#I, uh, hope it's obvious why we need this, but for file handling and repository initialization
import os
#Needed for SHA-1 when hashing objects
import hashlib
#Needed for lossless compression
import zlib
#Needed for named tuple
import collections
import struct
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