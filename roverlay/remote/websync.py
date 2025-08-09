# R overlay -- remote, websync
# -*- coding: utf-8 -*-
# Copyright (C) 2012-2014 André Erdmann <dywi@mailerd.de>
# Distributed under the terms of the GNU General Public License;
# either version 2 of the License, or (at your option) any later version.

from __future__ import division
from __future__ import print_function

"""websync, sync packages via http"""

__all__ = [ 'WebsyncPackageList', 'WebsyncRepo', ]

import errno
import contextlib
import re
import os
import socket
import sys

# py2 urllib2 vs py3 urllib.request
if sys.hexversion >= 0x3000000:
   import urllib.request as _urllib
   import urllib.error   as _urllib_error
else:
   import urllib2 as _urllib
   import urllib2 as _urllib_error

urlopen   = _urllib.urlopen
URLError  = _urllib_error.URLError
HTTPError = _urllib_error.HTTPError

from roverlay                  import config, digest, util
from roverlay.remote.basicrepo import BasicRepo
from roverlay.util.progressbar import DownloadProgressBar, NullProgressBar

# number of sync retries
#  changed 2014-02-15: does no longer include the first run
#
#  total number of sync tries := 1 + max ( MAX_WEBSYNC_RETRY, 0 )
#
MAX_WEBSYNC_RETRY = 3

VERBOSE = True

# FIXME: websync does not support package deletion

class WebsyncBase ( BasicRepo ):
   """Provides functionality for retrieving R packages via http.
   Not meant for direct usage."""

   HTTP_ERROR_RETRY_CODES = frozenset ({ 404, 410, 500, 503 })
   URL_ERROR_RETRY_CODES  = frozenset ({ errno.ETIMEDOUT, })
   RETRY_ON_TIMEOUT       = True
   PROGRESS_BAR_CLS       = None

   def __new__ ( cls, *args, **kwargs ):
      if cls.PROGRESS_BAR_CLS is None:
         cls.PROGRESS_BAR_CLS = (
            DownloadProgressBar if VERBOSE else NullProgressBar
         )
      return super ( WebsyncBase, cls ).__new__ ( cls )
   # --- end of __new__ (...) ---

   def __init__ ( self,
      name,
      distroot,
      src_uri,
      directory=None,
      digest_type=None
   ):
      """Initializes a WebsyncBase instance.

      arguments:
      * name        -- see BasicRepo
      * distroot    -- ^
      * src_uri     -- ^
      * directory   -- ^
      * digest_type -- if set and not None/"None":
                        verify packages using the given digest type
                        Supported digest types: 'md5'.
      """
      super ( WebsyncBase, self ) . __init__ (
         name=name,
         distroot=distroot,
         src_uri=src_uri,
         remote_uri=src_uri,
         directory=directory
      )

      if digest_type is None:
         self._digest_type = None

      elif str ( digest_type ).lower() in ( 'none', 'disabled', 'off' ):
         self._digest_type = None

      elif digest.digest_supported ( digest_type ):
         # setting a digest_type (other than None) expects package_list
         # to be a 2-tuple <package_file, digest sum> list,
         # else a list of package_files is expected.
         self._digest_type = digest_type

      else:
         raise Exception (
            "Unknown/unsupported digest type {}!".format ( digest_type )
         )

      self.timeout = config.get_or_fail ( "REPO.websync_timeout" )

      # download 8KiB per block
      self.transfer_blocksize = 8192
   # --- end of __init__ (...) ---

   def _fetch_package_list ( self ):
      """This function returns a list of packages to download."""
      raise Exception ( "method stub" )
   # --- end of _fetch_package_list (...) ---

   def _get_package ( self, package_file, src_uri, expected_digest ):
      """Gets a packages, i.e. downloads if it doesn't exist locally
      or fails verification (size, digest).

      arguments:
      * package_file    -- package file name
      * src_uri         -- uri for package_file
      * expected_digest -- expected digest for package_file or None (^=disable)
      """
      distfile = self.distdir + os.sep + package_file

      if self.skip_fetch ( package_file, distfile, src_uri ):
         if VERBOSE:
            print ( "Skipping fetch (early) for {f!r}".format ( f=distfile ) )
         return True


      with contextlib.closing (
         urlopen ( src_uri, None, self.timeout )
      ) as webh:
         #web_info = webh.info()

         expected_filesize = int ( webh.info().get ( 'content-length', -1 ) )

         if os.access ( distfile, os.F_OK ):
            # package exists locally, verify it (size, digest)
            fetch_required = False
            localsize      = os.path.getsize ( distfile )

            if localsize != expected_filesize:
               # size mismatch
               self.logger.info (
                  'size mismatch for {f!r}: expected {websize} bytes '
                  'but got {localsize}!'.format (
                     f         = package_file,
                     websize   = expected_filesize,
                     localsize = localsize
                  )
               )
               fetch_required = True

            elif expected_digest is not None:
               our_digest = digest.dodigest_file ( distfile, self._digest_type )

               if our_digest != expected_digest:
                  # digest mismatch
                  self.logger.warning (
                     '{dtype} mismatch for {f!r}: '
                     'expected {theirs} but got {ours} - refetching.'.format (
                        dtype  = self._digest_type,
                        f      = distfile,
                        theirs = expected_digest,
                        ours   = our_digest
                     )
                  )
                  fetch_required = True

         else:
            fetch_required = True

         if fetch_required:
            blocksize     = self.transfer_blocksize
            bytes_fetched = 0
            assert blocksize

            # unlink the existing file first (if it exists)
            #  this is necessary for keeping hardlinks intact (-> package mirror)
            util.try_unlink ( distfile )

            with \
               open ( distfile, mode='wb' ) as fh, \
               self.PROGRESS_BAR_CLS (
                  package_file.ljust(50), expected_filesize
            ) as progress_bar:

               progress_bar.update ( 0 )
               block = webh.read ( blocksize )

               while block:
                  # write block to file
                  fh.write ( block )
                  # ? bytelen
                  bytes_fetched += len ( block )

                  # update progress bar on every 4th block
                  #  blocks_fetched := math.ceil ( bytes_fetched / blocksize )
                  #
                  #  Usually, only the last block's size is <= blocksize,
                  #  so floordiv is sufficient here
                  #  (the progress bar gets updated for the last block anyway)
                  #
                  if 0 == ( bytes_fetched // blocksize ) % 4:
                     progress_bar.update ( bytes_fetched )

                  # get the next block
                  block = webh.read ( blocksize )
               # -- end while

               # final progress bar update (before closing the file)
               progress_bar.update ( bytes_fetched )
            # -- with

            if bytes_fetched == expected_filesize:
               if expected_digest is not None:
                  our_digest = digest.dodigest_file ( distfile, self._digest_type )

                  if our_digest != expected_digest:
                     # fetched package's digest does not match the expected one,
                     # refuse to use it
                     self.logger.warning (
                        'bad {dtype} digest for {f!r}, expected {theirs} but '
                        'got {ours} - removing this package.'.format (
                           dtype  = self._digest_type,
                           f      = distfile,
                           theirs = expected_digest,
                           ours   = our_digest
                        )
                     )
                     # package removed? -> return success (True/False)
                     return util.try_unlink ( distfile )
                  # -- end if <compare digest>
               # -- end if <have digest?>

            else:
               return False
            # -- end if <enough bytes fetched?>
         elif VERBOSE:
            print ( "Skipping fetch for {f!r}".format ( f=distfile ) )

      return self._package_synced ( package_file, distfile, src_uri )
   # --- end of get_package (...) ---

   def _package_synced ( self, package_filename, distfile, src_uri ):
      """Called when a package has been synced (=exists locally when
      _get_package() is done).

      arguments:
      * package_filename --
      * distfile         --
      * src_uri          --
      """
      return True
   # --- end of _package_synced (...) ---

   def _sync_packages ( self ):
      """Fetches the package list and downloads the packages."""
      package_list = self._fetch_package_list()

      # empty/unset package list
      if not package_list:
         self.logger.info (
            'Repo {name}: nothing to sync - package list is empty.'.format (
               name=self.name
            )
         )
         return True

      util.dodir ( self.distdir, mkdir_p=True )

      if VERBOSE:
         print ( "{:d} files to consider.".format ( len(package_list) ) )

      success = True

      if self._digest_type is not None:
         for package_file, expected_digest in package_list:
            src_uri  = self.get_src_uri ( package_file )

            if not self._get_package (
               package_file, src_uri, expected_digest
            ):
               success = False
               break
      else:
         for package_file in package_list:
            src_uri  = self.get_src_uri ( package_file )

            if not self._get_package (
               package_file, src_uri, expected_digest=None
            ):
               success = False
               break

      return success
   # --- end of _sync_packages (...) ---

   def _dosync ( self ):
      """Syncs this repo."""
      retry_count = 0
      want_retry  = True
      retval_tmp  = None
      retval      = None
      max_retry   = max ( MAX_WEBSYNC_RETRY, 0 ) + 1

      while want_retry and retry_count < max_retry:
         retry_count += 1
         want_retry   = False

         try:
            retval_tmp = self._sync_packages()

         except HTTPError as err:
            # catch some error codes that are worth a retry
            if err.code in self.HTTP_ERROR_RETRY_CODES:
               self.logger.info (
                  'sync failed with http error code {:d}. '
                  'Retrying...'.format ( err.code )
               )
               want_retry = True
            else:
               self.logger.error (
                  "got an unexpected http error code: {:d}".format ( err.code )
               )
               self.logger.exception ( err )
               retval = False
               #break

         except URLError as err:
            if isinstance ( err.reason, socket.timeout ):
               if self.RETRY_ON_TIMEOUT:
                  self.logger.info ( 'Connection timed out (#1). Retrying...' )
                  want_retry = True
               else:
                  self.logger.error ( 'Connection timed out (#1).' )
                  self.logger.exception ( err )
                  retval = False
                  #break

            elif hasattr ( err.reason, 'errno' ):
               if err.reason.errno in self.URL_ERROR_RETRY_CODES:
                  self.logger.info (
                     'sync failed with an url error (errno {:d}). '
                     'Retrying...'.format ( err.reason.errno )
                  )
                  want_retry = True
               else:
                  self.logger.error (
                     "got an unexpected url error code: {:d}".format (
                        err.reason.errno
                     )
                  )
                  self.logger.exception ( err )
                  retval = False
                  #break
            else:
               self.logger.error ( "got an unexpected url error." )
               self.logger.exception ( err )
               retval = False
               #break

         except socket.timeout as err:
            if self.RETRY_ON_TIMEOUT:
               self.logger.info ( 'Connection timed out (#2). Retrying...' )
               want_retry = True
            else:
               self.logger.error ( 'Connection timed out (#2).' )
               self.logger.exception ( err )
               retval = False
               #break

         except KeyboardInterrupt:
            #sys.stderr.write ( "\nKeyboard Interrupt\n" )
            #if RERAISE_INTERRUPT ...
            #retval = False
            raise

         except Exception as err:
            self.logger.exception ( err )
            retval = False
            #break

         else:
            retval = retval_tmp
      # -- end while

      if want_retry:
         self.logger.error (
            'Repo {name} cannot be used for ebuild creation: '
            'retry count exhausted.'.format ( name=self.name )
         )
         return False

      elif retval is None:
         self.logger.error (
            'Repo {name} cannot be used for ebuild creation: '
            'did not try to sync (max_retry={max_retry:d})'.format (
               name=self.name, max_retry=max_retry
            )
         )
         return False

      elif retval:
         return True

      else:
         self.logger.error (
            'Repo {name} cannot be used for ebuild creation due to errors '
            'while syncing.'.format ( name=self.name )
         )
         return False
   # --- end of _dosync (...) ---

   def skip_fetch ( self, package_filename, distfile, src_uri ):
      """Returns True if downloading of a package file should be skipped,
      else False. Called _before_ opening a web handle (urlopen()).

      arguments:
      * package_filename --
      * distfile         --
      * src_uri          --
      """
      return False
   # --- end of skip_fetch (...) ---

# --- end of WebsyncBase ---



class WebsyncRepo ( WebsyncBase ):
   """Sync a http repo using its PACKAGES file."""
   # FIXME: hardcoded for md5

   def __init__ ( self,
      pkglist_uri=None,
      pkglist_file=None,
      *args,
      **kwargs
   ):
      """Initializes a WebsyncRepo instance.

      arguments:
      * pkglist_uri      -- if set and not None: uri of the package list file
      * pkglist_file     -- if set and not None: name of the package list file,
                            this is used to calculate the pkglist_uri
                            pkglist_uri = <src_uri>/<pkglist_file>
      * *args / **kwargs -- see WebsyncBase / BasicRepo

      pkglist file: this is a file with debian control file-like syntax
                    listing all packages.
      Example: http://www.omegahat.org/R/src/contrib/PACKAGES (2012-07-31)
      """
      super ( WebsyncRepo, self ) . __init__ ( *args, **kwargs )

      if self._digest_type is None:
         self.FIELDREGEX = re.compile (
            '^\s*(?P<name>(package|version))[:]\s*(?P<value>.+)',
            re.IGNORECASE
         )
      else:
         # used to filter field names (package,version,md5sum)
         self.FIELDREGEX = re.compile (
            '^\s*(?P<name>(package|version|md5sum))[:]\s*(?P<value>.+)',
            re.IGNORECASE
         )

      self.pkglist_uri = pkglist_uri or self.get_src_uri ( pkglist_file )
      if not self.pkglist_uri:
         raise Exception ( "pkglist_uri is unset!" )

      self._synced_packages = set()
   # --- end of __init__ (...) ---

   def _fetch_package_list ( self ):
      """Returns the list of packages to be downloaded.
      List format:
      * if digest verification is enabled:
         List ::= [ ( package_file, digest ), ... ]
      * else
         List ::= [ package_file, ... ]
      """

      def generate_pkglist ( fh ):
         """Generates the package list using the given file handle.

         arguments:
         * fh -- file handle to read from
         """
         info = dict()

         max_info_len = 3 if self._digest_type is not None else 2

         for match in (
            filter (
               None,
               (
                  self.FIELDREGEX.match (
                     l if isinstance ( l, str ) else l.decode()
                  )
                  for l in fh.readlines()
               )
            )
         ):
            name, value = match.group ( 'name', 'value' )
            info [name.lower()] = value

            if len ( info ) == max_info_len:

               pkgfile = '{name}_{version}.tar.gz'.format (
                  name=info ['package'], version=info ['version']
               )

               if self._digest_type is not None:
                  yield ( pkgfile, info ['md5sum'] )
                  #yield ( pkgfile, ( 'md5', info ['md5sum'] ) )
               else:
                  yield pkgfile

               info.clear()
      # --- end of generate_pkglist (...) ---

      package_list = ()
      with contextlib.closing (
         urlopen ( self.pkglist_uri, None, self.timeout )
      ) as webh:
         content_type = webh.info().get ( 'content-type', None )

         # A page without content_type is just text/plain.
         if content_type != 'text/plain' and (content_type is not None):
            print (
               "content type {!r} is not supported!".format ( content_type )
            )
         else:
            package_list = list ( generate_pkglist ( webh ) )
      # -- end with

      return package_list
   # --- end fetch_pkglist (...) ---

   def skip_fetch ( self, package_filename, distfile, src_uri ):
      """Returns True if downloading of a package file should be skipped,
      else False. Called _before_ opening a web handle (urlopen()).

      arguments:
      * package_filename --
      * distfile         --
      * src_uri          --
      """
      return distfile in self._synced_packages
   # --- end of skip_fetch (...) ---


   def _package_synced ( self, package_filename, distfile, src_uri ):
      """Called when a package has been synced (=exists locally when
      _get_package() is done).

      arguments:
      * package_filename --
      * distfile         --
      * src_uri          --
      """
      self._synced_packages.add ( distfile )
      return True
   # --- end of _package_synced (...) ---

# --- end of WebsyncRepo ---


class WebsyncPackageList ( WebsyncBase ):
   """Sync packages from multiple remotes via http. Packages uris are read
   from a file."""

   # retry on 404 makes no sense for this sync type since a local package list
   # is used
   HTTP_ERROR_RETRY_CODES = frozenset ({ 410, 500, 503 })

   def __init__ ( self, pkglist_file, *args, **kwargs ):
      """Initializes a WebsyncPackageList instance.

      arguments:
      * pkglist_file     -- path to the package list file that lists
                            one package http uri per line
      * *args / **kwargs -- see WebsyncBase, BasicRepo
      """
      super ( WebsyncPackageList, self ) . __init__ ( *args, **kwargs )

      # len (pkglist_file) == 0: raise implicit Exception since
      # pkglist_file is not set

      if pkglist_file [0] == '~':
         self._pkglist_file = os.path.abspath (
            os.path.expanduser ( pkglist_file )
         )
      else:
         self._pkglist_file = os.path.abspath ( pkglist_file )

      del self.src_uri

      self._synced_packages = set()

   # --- end of __init__ (...) ---

   def _fetch_package_list ( self ):
      """Returns the package list.
      Format:
      pkglist ::= [ ( package_file, src_uri ), ... ]
      """
      pkglist = list()
      with open ( self._pkglist_file, mode='r' ) as fh:
         for line in fh.readlines():
            src_uri = line.strip()
            if src_uri:
               pkglist.append ( (
                  src_uri.rpartition ( '/' ) [-1],
                  src_uri
               ) )

      return pkglist
   # --- end of _fetch_package_list (...) ---

   def _package_synced ( self, package_filename, distfile, src_uri ):
      self._synced_packages.add ( ( package_filename, src_uri ) )
      return True
   # --- end of _package_synced (...) ---

   def skip_fetch ( self, package_filename, distfile, src_uri ):
      """Returns True if downloading of a package file should be skipped,
      else False. Called _before_ opening a web handle (urlopen()).

      arguments:
      * package_filename --
      * distfile         --
      * src_uri          --
      """
      return ( package_filename, distfile ) in self._synced_packages
   # --- end of skip_fetch (...) ---

   def scan_distdir ( self, log_bad=True, **kwargs_ignored ):
      for package_filename, src_uri in self._synced_packages:
         pkg = self._package_nofail (
            log_bad,
            filename = package_filename,
            origin   = self,
            src_uri  = src_uri
         )
         if pkg is not None:
            yield pkg
   # --- end of scan_distdir (...) ---

   def _nosync ( self ):
      """nosync - report existing packages"""
      for package_file, src_uri in self._fetch_package_list():
         distfile = self.distdir + os.sep + package_file
         if os.access ( distfile, os.F_OK ):
            self._package_synced ( package_file, distfile, src_uri )

      return True
   # --- end of _nosync (...) ---

   def _sync_packages ( self ):
      """Fetches package files."""
      package_list = self._fetch_package_list()

      # empty/unset package list
      if not package_list:
         self.logger.info (
            'Repo {name}: nothing to sync - package list is empty.'.format (
               name=self.name
            )
         )
         return True

      util.dodir ( self.distdir, mkdir_p=True )

      success = True

      if VERBOSE:
         print ( "{:d} files to consider.".format ( len(package_list) ) )

      for package_file, src_uri in package_list:
         if not self._get_package (
            package_file, src_uri, expected_digest=None
         ):
            success = False
            break

      return success
   # --- end of _sync_packages (...) ---
