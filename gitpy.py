#I, uh, hope it's obvious why we need this, but for file handling and repository initialization
import os
#used for determining object type
import enum
#Needed for SHA-1 when hashing objects
import hashlib
#Needed for lossless compression
import zlib
#Needed for named tuple
import collections
import struct
#Used for commits
import time
#Used for talking with git servers
import urllib.request
import stat
#needed to handle commands
import argparse

"""
Goal is to be able to create, add, commit, and push to a server (github) by the end of the week.
These are the basic functions of a github client.
"""

#Two basic helper functions we'll use frequently enough

#Writes data to file at path
def write_file(path, data):
    with open(path, "wb") as f:
        f.write(data)
#Reads from file at path
def read_file(path):
    with open(path, "r") as f:
        return f.read()


#Craeate directory for repo and initialize .git directory
def init(repo):
    """
    What happens when you run "init"?
    a couple of things:
    1. if the command is just "init" it adds a .git file to the current folder and treats that as the directory
    2. if the command is "init directory_name" it makes a directory in the os called "directory_name" and adds the .git to that
    we'll implement 2 for the moment, then round back and add in 1 once we have something basic up and running
    """

    os.mkdir(repo)
    """
    os.path.join isn't a method I use often, and always have to look up to remind myself how it functions
    os.path.join is so critical to this project, I'm just going to include a blurb about it here.

    it basically joins path components into a single absolute path,
    so the below line of code will produce: repo/.git
    this is simple but devious, say we have an os.join like
    os.path.join(repo, '.git', '\objects'), then the output will be just '\objects'
    because \objects is an absolute path, and resets the earlier components.

    It's good convention to use os.path.join (and honestly, something I should use more often), since it inserts the
    os appropriate seperator when it's called.
    """
    os.mkdir(os.path.join(repo, '.git'))
    for name in ['objects', 'refs', 'refs/heads']:
        os.mkdir(os.path.join(repo, '.git', name))
    write_file(os.path.join(repo, '.git', 'HEAD'), b'ref: refs/heads/maser')
    #initialized empty repository in path_to_directory is gitbash's convention
    print("Initialized empty repository in {}".format(repo))


"""
Github has three types of objects:
blobs (ordinary files),
commits,
and trees (used for representing the state of a directory)

Each object has a header including the type and size in bytes, followed by a NUL byte,
and finally the file's data bytes. (I might borrow including the type in the header for my C database...)

After making the header adding the NUL byte and then the data bytes, the file gets zlib-compressed (open source, 
lossless compression: https://en.wikipedia.org/wiki/Zlib) then it gets written to .git/objects/ab/cd... 
where ab could be the first two characters and cd is the rest of the hash
of a 40-character SHA-1 hash (Secure hash algorithm 1: https://en.wikipedia.org/wiki/SHA-1)
"""

class ObjectType(enum.Enum):
    commit = 1
    tree = 2
    blob = 3

#Hash an object of a given type then write to store (if write True), return the hash
def hash_object(data, object_type, write=True):
    #Create the header with object type and size of the data
    header = '{} {}'.format(object_type, len(data)).encode()
    #add the null bit and then the data
    full_data = header + b'\x00' + data
    sha1 = hashlib.sha1(full_data).hexdigest()
    #If True, write data to store
    if write:
        path = os.path.join('.git', 'objects', sha1[:2], sha1[2:])
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            write_file(path, zlib.compress(full_data))
    return sha1

"""Note that from the above function we can write find and read object functions:
finding obviously just requires searching for the hash prefix and the rest of the hash, and we know how the header
is organized so we just find the object and read out it's type and size."""

#Find object with sha-1 prefix and return path to object or raise value error (if no or multiple objects have same prefix)
def find_object(sha1_prefix):
    if len(sha1_prefix) < 2:
        raise ValueError('Hash prefix must be 2 or more characters')
    #remember the layout is .git/objects/first 2 characters of sha1/rest of sha1
    obj_dir = os.path.join('.git', 'objects', sha1_prefix[:2])
    rest = sha1_prefix[2:]
    objects = [name for name in os.listdir(obj_dir) if name.startswith(rest)]
    if not objects:
        raise ValueError('object {!r} not found'.format(sha1_prefix))
    if len(objects >= 2):
        raise ValueError('Multiple objects ({}) with prefix {!r}'.format(len(objects), sha1_prefix))
    return os.path.join(obj_dir, objects[0])

#Read object with given sha1 prefix and return a tuple of object_type, data_bytes
def read_object(sha1_prefix):
    path = find_object(sha1_prefix)
    full_data = zlib.decompress(read_file(path))
    nul_index = full_data.index(b'\x00')
    header = full_data[:nul_index]
    obj_type, size_str = header.decode().split()
    size = int(size_str)
    data = full_data[nul_index + 1:]
    assert size == len(data), 'expected size {}, got {} bytes'.format(size, len(data))
    return (obj_type, data)

"""Next is the git index, but what is the index anyways?:
it's basically the staging area, it holds staged changes that are ready to be committed.
List of file entries, ordered by path, which contains path name, modification time, sha-1 hash.
It lists *all* files in the current tree, not just files being staged for commit right now

It's stored as a custom binary format, for each index the first 12 bytes are the header, the last 20 are the sha-1 hash of the rest of the index,
the bytes in between are index entries, each of the entries are 62 bytes plus path length and padding."""

#Struct for one entry in our git index (.git/index)

"""Explanation for each of the named entries in our tuple:
ctime (change time) = last time file's metadata was changed
mtime (modification time )= last time file's content was changed
ctime_s: file's ctime in seconds
ctime_n file's last ctime in nanoseconds
mtime_s: file's last mtime in seconds
dev: device number, identfies the device the file resides on
ino: inode number, uniquely identifies file on the device
mode: File mode, encodes type and permissions
uid: user id of the file owner
gid: groupd id of the file owner
size: file size in bytes
sha1: sha1 hash of file's contents, points to the blob on git's object database
flags: a 16-bit field with extra meta data
path: path relative to repository root"""

IndexEntry = collections.namedtuple('IndexEntry', [
    'ctime_s', 'ctime_n', 'mtime_s', 'dev', 'ino', 'mode',
    'uid', 'gid', 'size', 'sha1', 'flags', 'path',
])

#Read index file and return list of IndexEntry objects
def read_index():
    try:
        data = read_file(os.path.join('.git', 'index'))
    except FileNotFoundError:
        return []
    #remember the last 20 bytes are a checksum of the rest of the index's contents
    #so check the hash of the everything but the last 20 bytes of the file,
    #if that matches the last 20 bytes of the file, the index is valid.
    digest = hashlib.sha1(data[:-20]).digest()
    assert digest == data[-20:], 'invalid index checksum'
    #struct.unpack will interpret the first 12 bytes of the file
    #! indicates big-endian byte order
    #4s indicates a 4 byte string (should always be b'DIRC')
    #L represents a 4 byte unsigned integer
    #So !4sLL means the struct we're unpacking uses big-endian order, first you'll unpack a 4
    #byte string into signature, then a 4-byte int into version (should always be 2 currently), then one more into num_entries
    #out of the first 12 bytes of data.
    signature, version, num_entries = struct.unpack('!4sLL', data[:12])
    assert signature == b'DIRC', \
    'invalid index signature {}'.format(signature)
    assert version == 2, 'unknown index version {}'.format(version)
    #our index entries is everything between the header and last 20 bytes
    entry_data = data[12:-20]
    entries = []
    #i = current length of all entries before the current one
    #so the second entries fields' end can be found at i = len(entry_1) + 62
    i = 0
    #ensure we don't run past the entry_data len when unpacking
    while i + 62 < len(entry_data):
        #our fields are 62 bytes total
        #10 4 byte ints, a 20 length string, and a 2 byte char
        fields_end = i + 62
        #remember our tuple is current 10 ints, the 20 length sha1 hash
        #H is 2-byte unsigned short, which in this case represents the flags field
        fields = struct.unpack('!LLLLLLLLLL20sH', entry_data[i:fields_end])
        #since our path can be of an arbitrary length
        #we'll search for the NUL byte which signifies the end of the path
        #then we can just store the path as entry_data[fields_end:path_end]
        path_end = entry_data.index(b'\x00', fields_end)
        path = entry_data[fields_end:path_end]
        entry = IndexEntry(*(fields + (path.decode(),)))
        entries.append(entry)
        entry_len = ((62 + len(path) + 8) // 8) * 8
        i += entry_len
    assert len(entries == num_entries)
    return entries
    
#Implement ls_files to print all files in the index
#implement status to compare files in the index to the current directory tree, printing out what's new and deleted
#Implement diff which prints a diff of each modified file showing what's in the index against what's in the current working copy

"""Committing
performing a commit consists of writing two objects
first a tree object, a snapshot (remember distributed systems?)
of the current index/directory at the time of commit
A tree lists the hashes of the files (blobs) and sub-trees in a recursive manner
when a file changes the hash of the entire tree changes, but if subtree has been left
the same it'll be the same hash, so we can store changes in directory trees efficiently.

First we will implement write_tree which will write theese tree objects for commits"""

#Write tree object from current index
def write_tree():
    tree_entries = []
    for entry in read_index():
        assert '/' not in entry.path, \
        'currently only supports a single, top-level directory'
        mode_path = '{:o} {}'.format(entry.mode, entry.path).encode()
        tree_entry = mode_path + b'\x00' + entry.sha1
        tree_entries.append(tree_entry)
    return hash_object(b''.join(tree_entries), 'tree')

#while we're here, let's implement read_tree, just the reverse of write_tree

#read tree given SHA1 or data, return list of (mode, path, sha1) tuples
def read_tree(sha1=None, data=None):
    if sha1 is not None:
        obj_type, data = read_object(sha1)
        assert obj_type == 'tree'
    elif data is None:
        raise TypeError('must specify sha1 or data')
    i = 0
    entries = []
    for _ in range(1000):
        end = data.find(b'\x00', i)
        if end == -1:
            break
        mode_str, path = data[i:end].decode().split()
        mode = int(mode_str, 8)
        digest = data[end + 1:end + 21]
        entries.append((mode, path, digest.hex()))
        i = end + 1 + 20
    return entries

"""
Second is the commit object itself, this records the tree hash, parent commit,
author, timestamp, and commit message. Right now we'll only support a single linear branch

"""

#we'll need a function to capture our local master branch hash

#Gets current commit hash of local master branch.
def get_local_master_hash():
    master_path = os.path.join('.git', 'refs', 'heads', 'master')
    try:
        return read_file(master_path).decode().strip()
    except FileNotFoundError:
        return None


#commit the current state of the index to master with a given message. Returns hash of commit object
def commit(message, author):
    tree = write_tree()
    parent = get_local_master_hash()
    timestamp = int(time.mktime(time.localtime()))
    utc_offset = -time.timezone
    author_time = '{} {}{:02}{:02}'.format(timestamp, 
                                           '+' if utc_offset > 0 else '-',
                                           abs(utc_offset) // 3600,
                                           (abs(utc_offset) // 60) % 60)
    lines = ['tree ' + tree]
    if parent:
        lines.append('parent ' + parent)
    lines.append('author {} {}'.format(author, author_time))
    lines.append('committer {} {}'.format(author, author_time))
    lines.append('')
    lines.append(message)
    lines.append('')
    data = '\n'.join(lines).encode()
    sha1 = hash_object(data, 'commit')
    master_path = os.path.join('.git','refs','heads', 'master')
    write_file(master_path, (sha1 + '\n').encode())
    print('committed to master: {:7}'.format(sha1))
    return sha1

"""Interacting with a server
We need to interact with Github to push to it.
We need to query the server's master branch for what commit it's on,
determine what set of objects it needs to catch up to current local commit,
finally, update the remote's commit hash and send a pack file of the missing objects

This is referred to as smart protocol.

A key component of the transfer protocol is the pkt-line format,
a length-prefixed packet format for sending metadata (such as commit hashes).
Each line is a 4-digit hex + 4 to include the length of the length, then an additional 4 bytes of data
each line usually has an LF byte at the end. a length of 0000 indicates a section marker at the end of the data

here is an example to work from:
    001f# service=git-receive-pack000000b20000000000000000000000000000000000000000 capabilities^{}\x00 report-status delete-refs side-band-64k quiet atomic ofs-deltaagent=git/2.9.3~peff-merge-upstream-2-9-1788-gef730f7 0000

Clearly the next steps are to convert pkt-line data into a list of lines and vice versa
"""
#Extract list of lines from pkt-line data
def extract_lines(data):
    lines = []
    i = 0
    for _ in range(1000):
        line_length = int(data[i:i + 4], 16)
        line = data[i + 4: i + line_length]
        lines.append(line)
        if line_length == 0:
            i += 4
        else:
            i += line_length
        if i > len(data):
            break
    return lines

#Build pkt line from given lines to send to server
def build_lines_data(lines):
    result = []
    for line in lines:
        result.append('{:04x}'.format(len(line) + 5).encode())
        result.append(line)
        result.append(b'\n')
    #Don't forget the end of line length!
    result.append(b'0000')
    return b''.join(result)

"""Now that we have a way to unpack and also send data to the server
we need to implement a basic https request function"""

#Make authenticated http request to given url
def http_request(url, username, password, data=None):
    password_manager = urllib.request.HTTPPasswordMgerWithDefaultRealm()
    password_manager.add_password(None, url, username, password)
    auth_handler = urllib.request.HTTPBasicAuthHandler(password_manager)
    opener = urllib.request.build_opener(auth_handler)
    f = opener.open(url, data=data)
    return f.read()

#get commit hash of master branch, return SHA-1 hex or None if no remote commits
def get_remote_master_hash(git_url, username, password):
    url = git_url + '/info/refs?service=git-recieve-pack'
    response = http_request(url, username, password)
    lines = extract_lines(response)
    #This ensures we're getting what we're requesting from git
    assert lines[0] == b'# service=git-receive-pack\n'
    assert lines[1] == b''
    if lines[2][:40] == b'0' * 40:
        return None
    master_sha1, master_ref = lines[2].split(b'\x00')[0].split()
    assert master_ref == b'refs/heads/master'
    assert len(master_sha1) == 40
    return master_sha1.decode()


"""Ok, we can talk to the server,
now we need to determine what the server doesn't already have
So we will recursively find object hashes in a tree and commit
so we can compare them to the master branch"""

#Return set of SHA-1 hashes of all objects, including the hash of the tree itself
def find_tree_objects(tree_sha1):
    objects = {tree_sha1}
    for mode, path, sha1 in read_tree(sha1=tree_sha1):
        if stat.S_ISDIR(mode):
            objects.update(find_tree_objects(sha1))
        else:
            objects.add(sha1)
    return objects

#Return set of SHA-1 hashes of all objects in this commit, including the hash of the commit itself.
def find_commit_objects(commit_sha1):
    objects = {commit_sha1}
    obj_type, commit = read_object(commit_sha1)
    assert obj_type == 'commit'
    lines = commit.decode().splitlines()
    tree = next(l[5:45] for l in lines if l.startswith('tree '))
    objects.update(find_tree_objects(tree))
    parents = (l[7:47] for l in lines if l.startswith('parent '))
    for parent in parents:
        objects.update(find_commit_objects(parent))
    return objects

#Finally a function to determine what objects are missing

#return set of SHA-1 hashes of objects in local commit that aren't at remote
def find_missing_objects(local_sha1, remote_sha1):
    local_objects = find_commit_objects(local_sha1)
    #remote is empty, so it's everything in our directory
    if remote_sha1 is None:
        return local_objects
    remote_objects = find_commit_objects(remote_sha1)
    return local_objects - remote_objects

"""Now we can handle pushing
we need to send a pkt-line which says to update the master branch to this commit hash
then a pack file containing the content of all the missing objects we found with find_missing_objects

So what's a pack file?
it has a 12-byte header starting with PACK then each object is encoded with a variable-length size
then compressed using zlib, and finally a 20-byte hash of the entire pack file. Note that you can 
make the pack file size even smaller based on changes between objects, but that's something we may round back to"""

#encodes a single object for a pack file and returns the bytes
def encode_pack_object(obj):
    obj_type, data = read_object(obj)
    type_num = ObjectType[obj_type].value
    size = len(data)
    byte = (type_num << 4) | (size & 0x0f)
    size >>= 4
    header = []
    while size:
        header.append(byte | 0x80)
        byte = size & 0x7f
        size >>= 7
        header.append(byte)
        return bytes(header) + zlib.compress(data)

#Create pack file by encoding all objects an concatinating them, return bytes of the full pack file
def create_pack(objects):
    #12 byte header that has PACk in it
    header = struct.pack('!4sLL', b'PACK', 2, len(objects))
    body = b''.join(encode_pack_object(o) for o in sorted(objects))
    contents = header + body
    sha1 = hashlib.sha1(contents).digest()
    data = contents + sha1
    return data

#Push to master branch given git repo url
def push(git_url, username, password):
    remote_sha1 = get_remote_master_hash(git_url, username, password)
    local_sha1 = get_local_master_hash()
    missing = find_missing_objects(local_sha1, remote_sha1)
    lines = ['{} {} refs/heads/master\x00 report-status'.format(remote_sha1 or ('0' * 40), local_sha1).encode()]
    data = build_lines_data(lines) + create_pack(missing)
    url = git_url + '/git-recieve-pack'
    response = http_request(url, username, password, data=data)
    lines = extract_lines(response)
    assert lines[0] == b'unpack ok\n', \
        "expected line 1 b'unpack ok', got: {}".format(lines[0])

if __name__ == '__main__':
    #okay we're expecting something like 'py gitpy.py command'
    parser = argparse.ArgumentParser()
    sub_parsers = parser.add_subparsers(dest='command', metavar='command')
    sub_parsers.required = True