"""
Based on https://thepythoncorner.com/posts/2017-02-27-writing-a-fuse-filesystem-in-python/
"""

import sys
import os
import io
import math
from fuse import FUSE
from tinytag import TinyTag

from passthrough import *


class AudioMLFuseFS(Passthrough):
    def __init__(self, root, delim="#"):
        #print("loading")
        self.root = root
        self.delim = delim

    def _full_path(self, partial, return_time = False):
        og_part = partial
        if partial.startswith("/"):
            partial = partial[1:]
        
        if self.delim in partial:
            partial, time_stamps = partial.split(self.delim)
        else:
            time_stamps = ""
        
        path = os.path.join(self.root, partial)

        #Format of time_stamps is num-num
        if time_stamps != "":
            start, end = time_stamps.split("-")
            start = float(start)
            end = float(end)

            tag = TinyTag.get(path)
            
            if start < 0:
                start = 0
            if end > tag.duration:
                end = tag.duration
        else:
           start = 0
           end = -1 

        
        if return_time:
            return path, start, end
        #print(og_part, partial, path)    
        return path

    def _estimate_file_size(self, full_path, total_size, duration):
        #audio_data_size = int(audio_file.info.length * audio_file.info.bitrate * audio_file.info.channels / 8)
        tag = TinyTag.get(full_path)
        data_size = int(math.ceil(
            tag.duration * tag.bitrate * 1000 * tag.channels / 8
        ))
        
        # Header size could have extra info
        # Best to just tack it on
        header_size = total_size - data_size

        return int(header_size + data_size * duration / tag.duration), header_size, tag.duration

    def _getattr_real(self, full_path, fh=None):
        st = os.lstat(full_path)
        st = dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                     'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))
        return st

    def getattr(self, path, fh=None):
        full_path, start, end = self._full_path(path, return_time=True)
        st = self._getattr_real(full_path)

        if end != -1:
            #print(st["st_size"], end-start)
            size, _, _ = self._estimate_file_size(full_path, st["st_size"], end-start)
            # TODO figure out how to compute the estimated file sizes of diffrent file types
            st["st_size"] = size
            #print(st["st_size"], end-start)
        return st

    def open(self, path, flags):
        full_path = self._full_path(path)
        out = os.open(full_path, flags)
        #print(out)
        return out
    
    def read(self, path, length, offset, fh):
        full_path, start, end = self._full_path(path, return_time=True)
        st = self._getattr_real(full_path)
        sim_file_size, header_size, duration = self._estimate_file_size(full_path, st["st_size"], end-start)

        start_index_of_clip = int(start/duration * (st["st_size"] - header_size)) 

        #print(path, offset, length, fh)
        read_data = bytearray()
        if offset == 0:
            os.lseek(fh, offset, os.SEEK_SET)
            header_data = os.read(fh, header_size)
            #print(read_data, header_data)
            read_data.extend(bytearray(header_data))
            length -= header_size
            offset += header_size
        
        os.lseek(fh, offset + start_index_of_clip, os.SEEK_SET)
        audio_data = os.read(fh, length)
        read_data.extend(bytearray(audio_data))
        #print(start, end, start_index_of_clip, offset, offset + start_index_of_clip, length, header_size, sim_file_size, st["st_size"])
        
        return bytes(read_data)
    

def main(mountpoint, root):
    FUSE(AudioMLFuseFS(root), mountpoint, nothreads=True,
         foreground=True, **{'allow_other': False, "nonempty": False})

if __name__ == '__main__':
    mountpoint = sys.argv[2]
    root = sys.argv[1]
    main(mountpoint, root)