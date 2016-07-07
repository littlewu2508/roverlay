# R overlay -- db, ( dist file ) => ( repo, repo file ) map
# -*- coding: utf-8 -*-
# Copyright (C) 2013 André Erdmann <dywi@mailerd.de>
# Distributed under the terms of the GNU General Public License;
# either version 2 of the License, or (at your option) any later version.

import errno
import logging

import roverlay.digest
import roverlay.util.common
import roverlay.util.fileio
import roverlay.util.objects
import roverlay.stats.collector


__all__ = [ 'DistMapInfo', 'FileDistMap', ]



class DistMapException ( Exception ):
   pass



class VirtualDistMapInfo ( object ):

   def __init__ ( self ):
      super ( VirtualDistMapInfo, self ).__init__()
      # references to objects that "own" (use, ...) this distfile
      self.backrefs    = set()
      self.add_backref = self.backrefs.add
   # --- end of __init__ (...) ---

   def is_volatile ( self ):
      return True

   def is_persistent ( self ):
      return False

   def deref_volatile ( self ):
      raise NotImplementedError()

   #def add_backref ( self, ref ): self.backrefs.add ( ref )

   def has_backref_to ( self, obj ):
      return any ( ref.deref_unsafe() is obj for ref in self.backrefs )
   # --- end of has_backref_to (...) ---

   def has_backrefs ( self ):
      return bool ( self.backrefs )

   def __eq__ ( self, other ):
      return self is other

   def __ne__ ( self, other ):
      return self is not other

   def get_repo_name ( self ):
      return None

# --- end of VirtualDistMapInfo ---


class DistMapInfo ( VirtualDistMapInfo ):
   """Distmap entry"""

   DIGEST_TYPE           = 'sha256'
   RESTORE_FROM_DISTFILE = '_'
   UNSET                 = 'U'

   @classmethod
   def from_package_info ( cls, p_info, allow_digest_create=True ):
      return cls (
         *p_info.get_distmap_value (
            allow_digest_create=allow_digest_create
         )
      )
   # --- end of from_package_info (...) ---

   @classmethod
   def volatile_from_package_info ( cls, p_info, backref=None ):
      instance = cls ( *p_info.get_distmap_value ( no_digest=True ) )
      return instance.make_volatile ( p_info, backref=backref )
   # --- end of volatile_from_package_info (...) ---

   def __init__ (
      self, distfile, repo_name, repo_file, sha256, volatile=None
   ):
      """Distmap entry constructor.

      arguments:
      * distfile  -- distfile path relative to the distroot
      * repo_name -- name of the repo that owns the package file
      * repo_file -- path of the package file relative to the repo
      * sha256    -- file checksum
      * volatile  -- a reference to a PackageInfo instance or None
                     None indicates that this entry should be persistent,
                     whereas "not None" indicates a "volatile" entry.
                     Defaults to None.
      """
      super ( DistMapInfo, self ).__init__()

      self.repo_name = repo_name if repo_name is not None else self.UNSET
      self.sha256    = sha256
      self.volatile  = volatile

      if repo_file == self.RESTORE_FROM_DISTFILE:
         self.repo_file = distfile
      else:
         self.repo_file = repo_file if repo_file is not None else self.UNSET
   # --- end of __init__ (...) ---

   def is_volatile ( self ):
      return self.volatile is not None
   # --- end of is_volatile (...) ---

   def is_persistent ( self ):
      return self.volatile is None
   # --- end of is_persistent (...) ---

   def make_volatile ( self, p_info, backref=None ):
      self.volatile = p_info.get_ref()
      self.sha256   = None
      if backref is not None:
         self.add_backref ( backref )
      return self
   # --- end of make_volatile (...) ---

   def make_persistent ( self ):
      p_info        = self.volatile.deref_safe()
      self.sha256   = p_info.make_distmap_hash()
      self.volatile = None
      return self
   # --- end of make_persistent (...) ---

   def deref_volatile ( self ):
      return None if self.volatile is None else self.volatile.deref_unsafe()
   # --- end of deref_volatile (...) ---

   @property
   def digest ( self ):
      return self.sha256
      #return getattr ( self, self.DIGEST_TYPE )
   # --- end of digest (...) ---

   def get_repo_name ( self ):
      return None if self.repo_name is self.UNSET else self.repo_name
   # --- end of get_repo_name (...) ---

   def get_repo_file ( self ):
      return None if self.repo_file is self.UNSET else self.repo_file
   # --- end of get_repo_file (...) ---

   def compare_digest ( self, package_info ):
      p_hash = package_info.make_distmap_hash()
      return ( bool ( p_hash == self.digest ), p_hash )
   # --- end of compare_digest (...) ---

   def __eq__ ( self, other ):
      if isinstance ( other, DistMapInfo ):
         return (
            self.sha256        == other.sha256
            and self.repo_name == other.repo_name
            and self.repo_file == other.repo_file
         )
      else:
         return super ( DistMapInfo, self ).__ne__ ( other )
   # --- end of __eq__ (...) ---

   def __ne__ ( self, other ):
      if isinstance ( other, DistMapInfo ):
         return (
            self.sha256       != other.sha256
            or self.repo_name != other.repo_name
            or self.repo_file != other.repo_file
         )
      else:
         return super ( DistMapInfo, self ).__ne__ ( other )
   # --- end of __ne__ (...) ---

   def to_str ( self, distfile, field_delimiter ):
      """Returns a distmap string.

      arguments:
      * distfile        --
      * field_delimiter -- char (or char sequence) that is used to separate
                           values
      """
      assert self.volatile is None
      return ( field_delimiter.join ((
         distfile,
         self.repo_name,
         (
            self.RESTORE_FROM_DISTFILE if self.repo_file == distfile
            else self.repo_file
         ),
         self.sha256
      )) )
   # --- end of to_str (...) ---

   def __str__ ( self ):
      return "{cls.__name__}<{repo_name}::{repo_file}>".format (
         cls = self.__class__,
         repo_name = ( self.get_repo_name() or "???" ),
         repo_file = ( self.get_repo_file() or "???" )
      )


# --- end of DistMapInfo ---


class _DistMapBase ( roverlay.util.objects.PersistentContent ):

   # { attr[, as_attr] }
   DISTMAP_BIND_ATTR = frozenset ({
      'get', 'keys', 'items', 'values', ( 'get', 'get_entry' ),
   })

   def __init__ ( self, *args, **kwargs ):
      super ( _DistMapBase, self ).__init__()
      self.logger   = logging.getLogger ( self.__class__.__name__ )
      self._distmap = dict()

      self.stats    = roverlay.stats.collector.static.distmap

      self._VIRTUAL_ENTRY = None

      self._rebind_distmap()

      self.update_only = True
   # --- end of __init__ (...) ---

   def __contains__ ( self, key ):
      return key in self._distmap
   # --- end of __contains__ (...) ---

   def __delitem__ ( self, key ):
      del self._distmap [key]
      self._file_removed ( key )
   # --- end of __delitem__ (...) ---

   def __getitem__ ( self, key ):
      return self._distmap [key]
   # --- end of __getitem__ (...) ---

   def __iter__ ( self ):
      return iter ( self._distmap )
   # --- end of __iter__ (...) ---

   def __len__ ( self ):
      return len ( self._distmap )
   # --- end of __len__ (...) ---

   def __bool__ ( self ):
      return True
   # --- end of __bool__ (...) ---

   def __nonzero__ ( self ):
      return self.__bool__()
   # --- end of __nonzero__ (...) ---

   def __setitem__ ( self, key, value ):
      if isinstance ( value, DistMapInfo ):
         self.add_entry ( key, value )
      elif hasattr ( value, 'get_distmap_value' ):
         self.add_entry ( key, DistMapInfo.from_package_info ( key ) )
      else:
         self.add_entry ( key, DistMapInfo ( key, *value ) )
   # --- end of __setitem__ (...) ---

   def _nondirty_file_added ( self, distfile ):
      self.stats.file_added()
   # --- end of _nondirty_file_added (...) ---

   def _file_added ( self, distfile ):
      self.stats.file_added()
      self.set_dirty()
   # --- end of _file_added (...) ---

   def _file_removed ( self, distfile ):
      self.stats.file_removed()
      self.set_dirty()
   # --- end of _file_removed (...) ---

   def _iter_persistent ( self ):
      for distfile, info in self._distmap.items():
         if info.is_persistent():
            yield ( distfile, info )
   # --- end of _iter_persistent (...) ---

   def _iter_volatile ( self ):
      for distfile, info in self._distmap.items():
         if info.is_volatile():
            yield ( distfile, info )
   # --- end of _iter_volatile (...) ---

   def _rebind_distmap ( self ):
      for attr in self.DISTMAP_BIND_ATTR:
         if isinstance ( attr, str ):
            setattr ( self, attr, getattr ( self._distmap, attr ) )
         else:
            setattr ( self, attr[1], getattr ( self._distmap, attr[0] ) )
   # --- end of _rebind_distmap (...) ---

   def add_distfile_owner ( self, backref, distfile, distfilepath=None ):
      entry = self.get_entry ( distfile )
      if entry is not None:
         entry.add_backref ( backref )
      else:
         try:
            entry = self.add_dummy_entry (
               distfile, distfilepath=distfilepath, log_level=True
            )
            entry.add_backref ( backref )
         except IOError as ioerr:
            if ioerr.errno == errno.ENOENT:
               entry = self.add_virtual_entry ( distfile, backref )
            else:
               raise

      # -- end if
      return entry
   # --- end of add_distfile_owner (...) ---

   def gen_info_lines ( self, field_delimiter ):
      for distfile, info in self._distmap.items():
         if info.is_persistent():
            yield info.to_str ( str ( distfile ), field_delimiter )
   # --- end of gen_info_lines (...) ---

   def get_distfile_slot ( self, package_dir, p_info ):
      distfile = p_info.get_distmap_key()
      entry    = self.get_entry ( distfile )

      if entry is None:
         # entry does not exist, create a new,volatile one
         self._distmap [distfile] = DistMapInfo.volatile_from_package_info (
            p_info, backref=package_dir.get_ref()
         )
         return 1
      elif entry.has_backref_to ( package_dir ):
         # entry exists and belongs to backref, nothing to do here
         # a revbump check might be necessary
         return 2
      elif entry.has_backrefs():
         # collision, should be resolved by the distroot
         return 0
      else:
         # distfile has no owner
         #  verify <>.repo, ...
         #
         entry.make_volatile ( p_info, package_dir.get_ref() )
         self._file_removed ( distfile )
         return 3
   # --- end of get_distfile_slot (...) ---

   def pkgdir_make_distfile_volatile ( self, package_dir, p_info ):
      """This is a helper function for
      roverlay.overlay.pkgdir.packagedir_base->PackageDirBase.add_package()
      ->package_try_replace() that might be removed in future and must not
      be used in any other code.

      It makes an existing distmap info entry belonging to package_dir/p_info
      volatile.

      arguments:
      * package_dir -- package dir that owns the distmap entry
      * p_info      -- package info object

      Returns: None (implicit)

      Raises:
      * KeyError if entry does not exist
      * DistMapException if entry is owned by package_dir
      """
      distfile  = p_info.get_distmap_key()
      entry     = self._distmap [distfile]

      if entry.has_backref_to ( package_dir ):
         entry.make_volatile ( p_info, package_dir.get_ref() )
         self._file_removed  ( distfile )

      else:
         raise DistMapException (
            "entry not owned by package dir: {entry}".format ( entry )
         )
      # -- end if

   # --- end of pkgdir_make_distfile_volatile (...) ---

   def check_revbump_necessary ( self, package_info ):
      """Tries to find package_info's distfile in the distmap and returns
      whether a revbump is necessary (True) or not (False).

      Compares checksums if distfile already exists.

      arguments:
      * package_info --
      """
      distfile = package_info.get_distmap_key()

      info = self._distmap.get ( distfile, None )
      if info is None:
         # new file, no revbump required
         return False
      elif info.get_repo_name() != package_info['origin'].name:
         # don't revbump if repo names don't match, this likely results in
         # infinite revbumps if a package is available from more than one repo
         return False
      elif info.compare_digest ( package_info ) [0] is True:
         # old digest == new digest, no revbump
         #  (package_info should be filtered out)
         return False
      else:
         # digest mismatch => diff
         return True
   # --- end of compare_digest (...) ---

   def get_hash_type ( self ):
      return DistMapInfo.DIGEST_TYPE
   # --- end of get_hash_types (...) ---

   def get_file_digest ( self, f ):
      """Returns a file checksum for the given file.

      arguments:
      * f --
      """
      return roverlay.digest.dodigest_file ( f, DistMapInfo.DIGEST_TYPE )
   # --- end of get_file_digest (...) ---

   def check_digest_integrity ( self, distfile, digest ):
      info = self._distmap.get ( distfile, None )

      if info is None:
         # file not found
         return 1
      elif info.digest == digest:
         # file OK
         return 0
      else:
         # bad checksum
         return 2
   # --- end of check_digest_integrity (...) ---

   def check_integrity ( self, distfile, distfilepath ):
      """Verifies a distfile by comparing its filepath with the distmap entry.
      Returns 1 if the file is not in the distmap, 2 if the file's checksum
      differs and 0 if the file is ok.

      arguments:
      * distfile     -- distfile path relative to the distroot
      * distfilepath -- absolute path to the distfile
      """
      if self._distmap.get ( distfile, None ) is None:
         return 1
      else:
         return self.check_digest_integrity (
            distfile, self.get_file_digest ( distfilepath )
         )
   # --- end of check_integrity (...) ---

   def delete ( self, key ):
      """Removes an entry from the distmap, whether persistent or not.

      arguments:
      * key -- distfile path relative to the distroot
      """
      del self._distmap [key]
      self._file_removed ( key )
   # --- end of delete (...) ---

   def try_delete ( self, key ):
      """Tries to remove an entry from the distmap.

      arguments:
      * key -- distfile path relative to the distroot
      """
      try:
         del self._distmap [key]
         self._file_removed ( key )
      except KeyError:
         pass
   # --- end of try_delete (...) ---

   def remove ( self, key ):
      """Removes a persistent entry from the distmap.

      arguments:
      * key -- distfile path relative to the distroot
      """
      if self._distmap[key].is_persistent():
         del self._distmap [key]
         self._file_removed ( key )
   # --- end of remove (...) ---

   def try_remove ( self, key ):
      """Tries to remove a persistent entry from the distfile.
      Does nothing if no entry found.

      arguments:
      * key -- distfile path relative to the distroot
      """
      try:
         if self._distmap[key].is_persistent():
            del self._distmap [key]
            self._file_removed ( key )
      except KeyError:
         pass
   # --- end of try_remove (...) ---

   def remove_volatiles ( self ):
      """Removes all non-persistent entries from the distmap."""
      volatiles = [ k for k, v in self._distmap.items() if v.is_volatile() ]
      for key in volatiles:
         del self._distmap [key]
   # --- end of remove_volatiles (...) ---

   def make_reverse_distmap ( self ):
      """Creates a reverse distmap that can be used to find repo files in the
      distdir.

      The reverse distmap has to be recreated after modifying the original
      distmap.
      """
      self._reverse_distmap = {
         ( kv[1].repo_name, kv[1].repo_file ): kv
            for kv in self._distmap.items()
      }
      return self._reverse_distmap
   # --- end of make_reverse_distmap (...) ---

   def release_reverse_distmap ( self ):
      """Removes the cached reverse distmap."""
      try:
         del self._reverse_distmap
      except AttributeError:
         pass
   # --- end of release_reverse_distmap (...) ---

   def lookup ( self, repo_name, repo_file ):
      """Tries to find a repo file in distroot.
      Returns a 2-tuple ( <relative distfile path>, <distmap entry> ) if
      repo file found, else None.

      Note: Creating a reverse distmap allows faster lookups.

      arguments:
      * repo_name -- name of the repo that owns repo_file
      * repo_file -- repo file (relative to repo directory)
      """
      if hasattr ( self, '_reverse_distmap' ):
         return self._reverse_distmap.get ( ( repo_name, repo_file ), None )
      else:
         for distfile, info in self._distmap.items():
            if info.repo_name == repo_name and info.repo_file == repo_file:
               return ( distfile, info )
            # -- end if
         else:
            return None
   # --- end of lookup (...) ---

   def add_entry ( self, distfile, distmap_info ):
      """Adds an entry to the distmap.

      arguments:
      * distfile     -- distfile path relative to the distroot
      * distmap_info -- distmap entry

      Returns: distmap_info
      """
      # FIXME: _file_removed()?
      if self.update_only:
         entry = self._distmap.get ( distfile, None )

         if entry is not None and entry == distmap_info:
            return entry

         else:
            self._distmap [distfile] = distmap_info
            if distmap_info.is_persistent():
               self._file_added ( distfile )
            del entry

      else:
         self._distmap [distfile] = distmap_info
         if distmap_info.is_persistent():
            self._file_added ( distfile )


      return distmap_info
   # --- end of add_entry (...) ---

   def add_entry_for ( self, p_info ):
      """Creates and adds an entry for a PackageInfo instance to the distmap.

      arguments:
      * p_info --

      Returns: created entry
      """
      distfile = p_info.get_distmap_key()
      entry    = self._distmap.get ( distfile, None )

      if entry is None or entry.deref_volatile() is not p_info:
         return self.add_entry (
            p_info.get_distmap_key(),
            DistMapInfo.from_package_info ( p_info )
         )
      else:
         entry.make_persistent()
         self._file_added ( distfile )
         return entry
   # --- end of add_entry_for (...) ---

   def add_entry_for_volatile ( self, p_info ):
      distfile    = p_info.get_distmap_key()
      entry       = self._distmap [distfile]
      entry_pinfo = entry.deref_volatile()

      if entry_pinfo is p_info:
         entry.make_persistent()
         self._file_added ( distfile )
         return entry

      elif not entry_pinfo:
         raise DistMapException (
            "entry for {dfile} is not volatile!".format ( dfile=distfile )
         )

      else:
         raise DistMapException (
            "entry for {dfile} is owned by {other_pkg}, not {pkg}!".format (
               dfile     = distfile,
               other_pkg = entry_pinfo,
               pkg       = p_info
            )
         )
   # --- end of add_entry_for_volatile (...) ---

   def add_dummy_entry (
      self, distfile, distfilepath=None, hashdict=None, log_level=None
   ):
      """Adds a dummy entry.
      Such an entry contains a checksum and a distfile, but no information
      about its origin (repo name/file).

      arguments:
      * distfile     -- distfile path relative to the distroot
      * distfilepath -- absolute path to the distfile
      * hashdict     -- dict with already calculated hashes
      * log_level    -- if not None: log entry creation with the given log
                        level (or INFO if log_level is True)

      Returns: created entry
      """
      if log_level is None or log_level is False:
         pass
      elif log_level is True:
         self.logger.info ( "adding dummy entry for " + distfile )
      else:
         self.logger.log ( log_level, "adding dummy entry for " + distfile )

      if hashdict and DistMapInfo.DIGEST_TYPE in hashdict:
         digest = hashdict [DistMapInfo.DIGEST_TYPE]
      else:
         digest = self.get_file_digest ( distfilepath )

      return self.add_entry (
         distfile, DistMapInfo ( distfile, None, None, digest )
      )
   # --- end of add_dummy_entry (...) ---

   def add_virtual_entry ( self, distfile, backref=None, log_level=True ):
      if log_level is None or log_level is False:
         pass
      else:
         log_msg =  (
            "adding virtual entry for {} - file does not exist!".format (
               distfile
            )
         )
         if log_level is True:
            self.logger.warning ( log_msg )
         else:
            self.logger.log ( log_level, log_msg )
      # -- end if <log_level>

      if self._VIRTUAL_ENTRY is None:
         self._VIRTUAL_ENTRY = VirtualDistMapInfo()

      if backref is not None:
         self._VIRTUAL_ENTRY.add_backref ( backref )

      return self.add_entry ( distfile, self._VIRTUAL_ENTRY )
   # --- end of add_virtual_entry (...) ---

# --- end of _DistMapBase ---


class FileDistMap ( roverlay.util.fileio.TextFile, _DistMapBase ):
   """A distmap that is read from / written to a file."""

   # the default info field separator
   FIELD_DELIMITER = '|'
   #FIELD_DELIMITER = ' '

   # file format (reserved for future usage)
   FILE_FORMAT = '0'

   @classmethod
   def get_default_compression ( cls ):
      return "bzip2" if cls.check_compression_supported ( "bzip2" ) else None
   # --- end of get_default_compression (...) ---

   def __init__ (
      self, distmap_file, distmap_compression=None, ignore_missing=False
   ):
      """Constructor for a distmap that stores its information to a file,
      optionally compressed.

      arguments:
      * distmap_file        -- file with distmap info entries
      * distmap_compression -- distmap file compression format (None: disable)
      * ignore_missing      -- do not fail if distmap file does not exist?

      raises: ValueError if distmap_compression not supported.
      """
      super ( FileDistMap, self ).__init__ (
         filepath=distmap_file, compression=distmap_compression
      )

      if ignore_missing:
         self.try_read()
      else:
         self.read()
   # --- end of __init__ (...) ---

   def get_header ( self ):
      return "<{d}<{fmt}".format (
         d=self.FIELD_DELIMITER, fmt=self.FILE_FORMAT
      )
   # --- end of get_header (...) ---

   def gen_info_lines ( self ):
      for distfile, info in self._distmap.items():
         if info.is_persistent():
            yield info.to_str ( str ( distfile ), self.FIELD_DELIMITER )
   # --- end of gen_info_lines (...) ---

   def gen_lines ( self ):
      """Generator that creates distmap file text lines."""
      # header
      yield self.get_header()
      for line in self.gen_info_lines():
         yield line
   # --- end of gen_lines (...) ---

   def _read_header ( self, line ):
      """Tries to parse a text line as distmap file header.
      Returns True if line was a header line, else False.

      arguments:
      * line --
      """
      if len ( line ) > 2 and line[0] == line[2]:
         # instance attr
         self.FIELD_DELIMITER = line[1]
         if len ( line ) > 3:
            self.FILE_FORMAT = line[3:]
         return True
      else:
         return False
   # --- end of _read_header (...) ---

   def parse_line ( self, line ):
      distfile, info = roverlay.util.common.headtail (
         line.split ( self.FIELD_DELIMITER )
      )
      self._distmap [distfile] = DistMapInfo ( distfile, *info )
      self._nondirty_file_added ( distfile )
      return True
   # --- end of parse_line (...) ---

   def parse_header_line ( self, line ):
      """Tries to parse a text line as distmap file header, else parses
      it as normal text line.

      arguments:
      * line --
      """
      if len ( line ) > 2 and line[0] == line[2]:
         # instance attr
         self.FIELD_DELIMITER = line[1]
         if len ( line ) > 3:
            self.FILE_FORMAT = line[3:]
         return True
      else:
         return self.parse_line ( line )
   # --- end of parse_header_line (...) ---

# --- end of FileDistMap ---
