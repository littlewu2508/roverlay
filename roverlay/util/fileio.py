# R overlay -- util, file read operations
# -*- coding: utf-8 -*-
# Copyright (C) 2012-2014 André Erdmann <dywi@mailerd.de>
# Distributed under the terms of the GNU General Public License;
# either version 2 of the License, or (at your option) any later version.

import mimetypes
import sys
import os.path
import shutil
import errno

import roverlay.util.common
import roverlay.util.objects
import roverlay.util.compression
import roverlay.strutil
from roverlay.strutil import bytes_try_decode
from roverlay.util.compression import \
   COMP_XZ, COMP_BZIP2, COMP_GZIP, LZMAError, \
   get_compress_open, check_compression_supported


_MIME = mimetypes.MimeTypes()
guess_filetype = _MIME.guess_type


def strip_newline ( s ):
   return s.rstrip ( '\n' )
# --- end of strip_newline (...) ---

def read_compressed_file_handle ( CH, preparse=None ):
   if preparse is None:
      for line in CH.readlines():
         yield bytes_try_decode ( line )
   elif preparse is True:
      for line in CH.readlines():
         yield strip_newline ( bytes_try_decode ( line ))
   else:
      for line in CH.readlines():
         yield preparse ( bytes_try_decode ( line ) )
# --- end of read_compressed_file_handle (...) ---

def read_text_file ( filepath, preparse=None, try_harder=True ):
   """Generator that reads a compressed/uncompressed file and yields text
   lines. Optionally preparses the rext lines.

   arguments:
   * filepath   -- file to read
   * preparse   -- function for (pre-)parsing lines
   * try_harder -- try known compression formats if file extension cannot
                   be detected (defaults to True)
   """

   ftype         = guess_filetype ( filepath )
   compress_open = get_compress_open ( ftype[1], None )

   if compress_open is not None:
      with compress_open ( filepath, mode='r' ) as CH:
         for line in read_compressed_file_handle ( CH, preparse ):
            yield line

      return

   elif try_harder:
      # guess_filetype detects file extensions only
      #
      #  try known compression formats
      #
      for comp in ( COMP_BZIP2, COMP_XZ, COMP_GZIP ):
         CH = None
         copen = get_compress_open ( comp, None )
         if copen is not None:
            try:
               CH      = copen ( filepath, mode='r' )
               creader = read_compressed_file_handle ( CH, preparse )
               # safely read first line only
               line    = next ( creader )

            except ( StopIteration, EOFError ):
               # empty file (?)
               CH.close()
               CH = None
               # *** FIXME: workaround ***
               # retry as normal file,
               #  EOFError may be caused by small plain text files, too
               # COULDFIX: ?empty compressed files?
               #return

            except IOError as ioerr:
               # failed to open (gzip, bzip2)
               if CH: CH.close()
               CH = None
               if ioerr.errno is not None:
                  raise

            except LZMAError as err:
               # failed to open (xz)
               if CH: CH.close()
               CH = None

            except:
               if CH: CH.close()
               raise

            else:
               yield line
               # read remaining lines
               for line in creader:
                  yield line
               CH.close()
               return
            # -- end try
         # -- end if
      # -- end for <comp>

   # -- end if <try to read filepath as compressed file>

   # file doesn't seem to be compressed (or not supported)
   with open ( filepath, 'rt' ) as FH:
      if preparse is None:
         for line in FH.readlines():
            yield line
      elif preparse is True:
         for line in FH.readlines():
            yield strip_newline ( line )
      else:
         for line in FH.readlines():
            yield preparse ( line )
# --- end of read_text_file (...) ---

def write_text_file (
   filepath, lines, compression=None, mode='wt',
   append_newlines=True, append_newline_eof=False, create_dir=True,
   newline='\n'
):
   compress_open = get_compress_open ( compression ) if compression else None
   lines_iter    = ( lines, ) if isinstance ( lines, str ) else lines

   if create_dir:
      roverlay.util.common.dodir_for_file ( filepath )

   if compress_open:
      NL = newline.encode()
      with compress_open ( filepath, mode.rstrip ( 'tu' ) ) as CH:
         for line in lines_iter:
            CH.write ( str ( line ).encode() )
            if append_newlines:
               CH.write ( NL )

         if append_newline_eof:
            CH.write ( NL )
   else:
      with open ( filepath, mode ) as FH:
         for line in lines_iter:
            FH.write ( str ( line ) )
            if append_newlines:
               FH.write ( newline )
         if append_newline_eof:
            FH.write ( newline )

   return True
# --- end of write_text_file (...) ---


class TextFile ( roverlay.util.objects.PersistentContent ):

   READ_PREPARSE   = True
   READ_TRY_HARDER = True

   @classmethod
   def get_default_compression ( cls ):
      return None
   # --- end of get_default_compression (...) ---

   @classmethod
   def check_compression_supported ( cls, compression ):
      return check_compression_supported ( compression )
   # --- end of check_compression_supported (...) ---

   def __init__ ( self, filepath, compression=None ):
      super ( TextFile, self ).__init__()

      self._filepath    = None
      self._compression = None

      self.first_line   = None
      self.lino         = None

      self.set_filepath ( filepath )
      self.set_compression ( compression )
   # --- end of __init__ (...) ---

   @roverlay.util.objects.abstractmethod
   def parse_line ( self, line ):
      return True
   # --- end of parse_line (...) ---

   def parse_header_line ( self, line ):
      return self.parse_line ( line )
   # --- end of parse_header_line (...) ---

   @roverlay.util.objects.abstractmethod
   def gen_lines ( self ):
      #yield ...
      return
   # --- end of gen_lines (...) ---

   def start_reading ( self ):
      pass
   # --- end of start_reading (...) ---

   def done_reading ( self ):
      pass
   # --- end of done_reading (...) ---

   def set_filepath ( self, filepath ):
      self._filepath = filepath
   # --- end of set_filepath (...) ---

   def set_compression ( self, compression ):
      if not compression or compression == 'none':
         self._compression = None
      elif compression == 'default':
         if __debug__:
            comp = self.get_default_compression()
            assert self.check_compression_supported ( comp )
            self._compression = comp
         else:
            self._compression = self.get_default_compression()
      elif self.check_compression_supported ( compression ):
         self._compression = compression
      else:
         raise ValueError (
            "unknown file compression {!r}".format ( compression )
         )
   # --- end of set_compression (...) ---

   def backup_file ( self, destfile=None, move=False, ignore_missing=False ):
      """Creates a backup copy of the file.

      arguments:
      * destfile       -- backup file path
                          Defaults to <dfile> + '.bak'.
      * move           -- move dfile (instead of copying)
      * ignore_missing -- return False if file does not exist instead of
                          raising an exception. Defaults to False.
      """
      dest = destfile or ( self._filepath + '.bak' )
      try:
         roverlay.util.dodir ( os.path.dirname ( dest ), mkdir_p=True )
         if move:
            shutil.move ( self._filepath, dest )
            return True
         else:
            shutil.copyfile ( self._filepath, dest )
            return True
      except IOError as ioerr:
         if ignore_missing and ioerr.errno == errno.ENOENT:
            return False
         else:
            raise
   # --- end of backup_file (...) ---

   def backup_and_write ( self,
      destfile=None, backup_file=None,
      force=False, move=False, ignore_missing=True
   ):
      """Creates a backup copy of the distmap file and writes the modified
      distmap afterwards.

      arguments:
      * destfile       -- file path to be written (defaults to self._filepath)
      * backup_file    -- backup file path (see backup_file())
      * force          -- enforce writing even if file content not modified
      * move           -- move distmap (see backup_file())
      * ignore_missing -- do not fail if the file does not exist when
                          creating a backup copy.
                          Defaults to True.
      """
      if force or self.dirty:
         self.backup_file (
            destfile=backup_file, move=move, ignore_missing=ignore_missing
         )
         return self.write ( filepath=destfile, force=True )
      else:
         return True
   # --- end of backup_and_write (...) ---

   def file_exists ( self ):
      """Returns True if the file exists, else False."""
      return os.path.isfile ( self._filepath )
   # --- end of file_exists (...) ---

   def try_read ( self, *args, **kwargs ):
      """Tries to read the file."""
      ret = None
      try:
         self.read ( *args, **kwargs )
      except IOError as ioerr:
         if ioerr.errno == errno.ENOENT:
            ret = False
         else:
            raise
      else:
         ret = True

      return ret
   # --- end of try_read (...) ---

   def read ( self, filepath=None ):
      """Reads the file.

      arguments:
      * filepath -- path to the distmap file (defaults to self.dbfile)
      """
      fpath = self._filepath if filepath is None else filepath

      self.start_reading()

      self.first_line = True
      self.lino       = 0
      for lino, line in enumerate (
         read_text_file ( fpath,
            preparse=self.READ_PREPARSE, try_harder=self.READ_TRY_HARDER
         )
      ):
         self.lino = lino
         if self.first_line:
            self.first_line = False
            # parse_header_line() can reset first_line to True
            self.parse_header_line ( line )
         else:
            self.parse_line ( line )

      if filepath is not None:
         self.set_dirty()

      self.done_reading()
   # --- end of read (...) ---

   def write ( self, filepath=None, force=False ):
      """Writes the file.

      arguments:
      * filepath -- path to the file to be written (defaults to self._filepath)
      * force    -- enforce writing even if file content not modified
      """
      if force or self.dirty or filepath is not None:
         fpath = self._filepath if filepath is None else filepath
         write_text_file (
            fpath, self.gen_lines(),
            compression=self._compression, create_dir=True
         )

         if filepath is None:
            self.reset_dirty()
         # else keep

         return True
      else:
         return False
   # --- end of write (...) ---

# --- end of TextFile ---
