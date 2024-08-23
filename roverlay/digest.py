# R overlay -- roverlay package, digest
# -*- coding: utf-8 -*-
# Copyright (C) 2012 André Erdmann <dywi@mailerd.de>
# Distributed under the terms of the GNU General Public License;
# either version 2 of the License, or (at your option) any later version.

"""provides digest related utility functions (e.g. md5sum_file())"""

__all__ = [
   'digest_compare', 'digest_comparator',
   'digest_supported', 'dodigest_file',
   'multihash', 'multihash_file',
   'md5sum_file', 'sha1_file', 'sha256_file', 'sha512_file',
   'whirlpool_file',
]

DEFAULT_BLOCKSIZE=16384


import hashlib

_HASH_CREATE_MAP = {
   'md5'       : hashlib.md5,
   'sha1'      : hashlib.sha1,
   'sha256'    : hashlib.sha256,
   'sha512'    : hashlib.sha512,
}

def hashlib_wrap ( name ):
   """Creates a wrapper that uses hashlib.new(<name>) for the given name.

   arguments:
   * name -- hash name, e.g. whirlpool
   """
   def wrapped ( *args, **kwargs ):
      return hashlib.new ( name, *args, **kwargs )
   # --- end of wrapped (...) ---

   h = hashlib.new
   wrapped.__dict__.update ( h.__dict__ )
   wrapped.__name__ = name
   wrapped.__doc__  = h.__doc__
   del h
   return wrapped
# --- end of hashlib_wrap (...) ---

def hashlib_supports ( name ):
   """Returns True if the given hash type is supported, else False.

   arguments:
   * name --
   """
   if name in getattr ( hashlib, 'algorithms_available', () ):
      # python 2's hashlib has no algorithms_available attribute
      return True
   else:
      ret = False
      try:
         hashlib.new ( name )
      except ValueError:
         pass
      else:
         ret = True
      return ret
# --- end of hashlib_supports (...) ---

if hashlib_supports ( 'whirlpool' ):
   _HASH_CREATE_MAP ['whirlpool'] = hashlib_wrap ( "whirlpool" )
else:
   import portage.util.whirlpool
   _HASH_CREATE_MAP ['whirlpool'] = portage.util.whirlpool.CWhirlpool

# -- end of imports / HASH_CREATE_MAP


def _generic_obj_hash (
   hashobj, fh, binary_digest=False, blocksize=DEFAULT_BLOCKSIZE
):
   block = fh.read ( blocksize )
   while block:
      hashobj.update ( block )
      block = fh.read ( blocksize )

   return hashobj.digest() if binary_digest else hashobj.hexdigest()
# --- end of _hashsum_generic (...) ---

def _generic_file_obj_hash (
   hashobj, filepath, binary_digest=False, blocksize=DEFAULT_BLOCKSIZE
):
   ret = None
   with open ( filepath, 'rb' ) as fh:
      ret = _generic_obj_hash ( hashobj, fh, binary_digest, blocksize )
   return ret
# --- end of _generic_file_obj_hash (...) ---

def multihash (
   fh, hashlist, binary_digest=False, blocksize=DEFAULT_BLOCKSIZE
):
   """Calculates multiple digests for an already openened file and returns the
   resulting hashes as dict.

   arguments:
   * fh            -- file handle
   * hashlist      -- iterable with hash names (e.g. md5)
   * binary_digest -- whether the hashes should be binary or not
   * blocksize     -- block size for reading
   """
   hashobj_dict = {
      h: _HASH_CREATE_MAP[h]() for h in hashlist
   }
   block = fh.read ( blocksize )
   while block:
      for hashobj in hashobj_dict.values():
         hashobj.update ( block )
      block = fh.read ( blocksize )

   if binary_digest:
      return { h: hashobj.digest() for h, hashobj in hashobj_dict.items() }
   else:
      return { h: hashobj.hexdigest() for h, hashobj in hashobj_dict.items() }
# --- end of multihash (...) ---

def multihash_file ( filepath, digest_types, **kwargs ):
   """Calculates multiple digests for the given file path.

   Returns an empty dict if digest_types is empty.

   arguments:
   * filepath     --
   * digest_types --
   * **kwargs     -- passed to multihash()
   """
   if digest_types:
      hashdict = None
      with open ( filepath, mode='rb' ) as fh:
         hashdict = multihash ( fh, digest_types, **kwargs )
      return hashdict
   else:
      return dict()
# --- end of multihash_file (...) ---

def md5sum_file ( filepath, **kw ):
   """Returns the md5 sum for a file."""
   return _generic_file_obj_hash ( hashlib.md5(), filepath, **kw )
# --- end of md5sum_file (...) ---

def sha1_file ( filepath, **kw ):
   return _generic_obj_hash ( hashlib.sha1(), filepath, **kw )
# --- end of sha1_file (...) ---

def sha256_file ( filepath, **kw ):
   return _generic_obj_hash ( hashlib.sha256(), filepath, **kw )
# --- end of sha256_file (...) ---

def sha512_file ( filepath, **kw ):
   return _generic_obj_hash ( hashlib.sha512(), filepath, **kw )
# --- end of sha512_file (...) ---

def whirlpool_file ( filepath, **kw ):
   return _generic_obj_hash (
      portage.util.whirlpool.new(), filepath, **kw
   )
# --- end of whirlpool_file (...) ---

def digest_supported ( digest_type ):
   """Returns True if the given digest type is supported, else False."""
   return digest_type in _HASH_CREATE_MAP
# --- digest_supported (...) ---

def dodigest_file ( _file, digest_type, **kwargs ):
   return _generic_file_obj_hash (
      hashobj       = _HASH_CREATE_MAP [digest_type](),
      filepath      = _file,
      **kwargs
   )
# --- end of dodigest_file (...) ---

def digest_compare ( digest, digest_type, filepath, **kwargs ):
   return digest == dodigest_file ( filepath, digest_type, **kwargs )
# --- end of digest_compare (...) ---

# digest_comparator :: digest_type -> digest -> ( filepath, ... ) -> bool
digest_comparator = (
   lambda digest_type : (
      lambda digest : (
         lambda filepath, *args, **kwargs : digest_compare (
            digest, digest_type, *args, **kwargs
         )
      )
   )
)
