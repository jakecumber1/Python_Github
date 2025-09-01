#I, uh, hope it's obvious why we need this, but for file handling and repository initialization
import os
#Needed for SHA-1 when hashing objects
import hashlib
#Needed for lossless compression
import zlib
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