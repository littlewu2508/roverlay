# R overlay -- ebuild creation
# -*- coding: utf-8 -*-
# Copyright (C) 2012, 2013 André Erdmann <dywi@mailerd.de>
# Distributed under the terms of the GNU General Public License;
# either version 2 of the License, or (at your option) any later version.

"""ebuild creation

This module puts all parts of the ebuild package together and provides
easy-to-use ebuild creation access.
"""

__all__ = [ 'EbuildCreation', ]

#TODO/COULDFIX: merge creation.py and depres.py

import logging

from roverlay.ebuild import depres, ebuilder, evars

LOGGER = logging.getLogger ( 'EbuildCreation' )

# FALLBACK_DESCRIPTION is used as DESCRIPTION variable (if not None)
#  if the R package's desc data has no Title/Description
FALLBACK_DESCRIPTION = evars.DESCRIPTION ( "<none>" )
#FALLBACK_DESCRIPTION = None


class EbuildCreation ( object ):
   """Used to create an ebuild using DESCRIPTION data."""

   def __init__ ( self, package_info, err_queue, depres_channel_spawner=None ):
      """Initializes the creation of an ebuild.

      arguments:
      * package_info           --
      * depres_channel_spawner -- function that returns a communication
                                   channel to the resolver
      """
      self.package_info = package_info
      self.package_info.set_readonly()

      self.logger = LOGGER.getChild ( package_info ['name'] )

      # > 0 busy/working; 0 == done,success; < 0 done,fail
      self.status  = 1
      # function reference that points to the next task
      self._resume = self._run_prepare
      self.paused  = False

      self.depres_channel_spawner = depres_channel_spawner

      self.err_queue = err_queue

      #self.use_expand_flag_names = None
   # --- end of __init__ (...) ---

   def _get_depres_channel ( self, **channel_kw ):
      return self.depres_channel_spawner (
         package_ref=self.package_info.get_ref(), **channel_kw
      )
   # --- end of _get_depres_channel (...) ---

   def done    ( self ) : return self.status  < 1
   def busy    ( self ) : return self.status  > 0
   def success ( self ) : return self.status == 0
   def fail    ( self ) : return self.status  < 0

   def run ( self, stats ):
      """Creates an ebuild and stores it directly in the assigned PackageInfo
      instance. Returns None (implicit).

      arguments:
      * stats --
      """
      # FIXME: totally wrong __doc__

      # Note:
      #  only stats details are allowed to be incremented/decremented here
      #  (except for "Exception caught", where pkg_fail is incremented)
      #

      if self.status < 1:
         raise Exception ( "Cannot run again." )

      try:
         self.paused = False
         while self.status > 0 and not self.paused:
            resume_func  = self._resume
            self._resume = None
            if not resume_func ( stats ):
               s = self.status
               if s > 0:
                  s *= (-1)
                  self.status = s
               # else already set by _resume()
               self.logger.info (
                  'Cannot create an ebuild for this package '
                  '(status={:d}).'.format ( s )
               )

         if self.status == 0:
            self.logger.debug ( "Ebuild is ready." )
            return True
         else:
            return False
      except:
         # set status to "fail due to exception"
         self.status = -10
         stats.pkg_fail.inc ( "exception" )
         raise
   # --- end of run (...) ---

   def _run_prepare ( self, stats ):
      self.status = 2

      p_info = self.package_info

      # read DESCRIPTION data
      p_info.update_now ( make_desc_data=True )
      if p_info ['desc_data'] is None:
         self.logger.warning (
            'desc empty - cannot create an ebuild for this package.'
         )
         stats.pkg_fail.inc_details ( "empty_desc" )
         return False
      else:
         # resolve dependencies
         dep_resolution = depres.EbuildDepRes (
            self.package_info, self.logger,
            run_now=True, depres_channel_spawner=self._get_depres_channel,
            err_queue=self.err_queue
         )
         if dep_resolution.success():
            self.dep_resolution = dep_resolution

            self.selfdeps = frozenset (
               dep_resolution.get_mandatory_selfdeps()
            )
            self.optional_selfdeps = frozenset (
               dep_resolution.get_optional_selfdeps()
            )

            if (
               p_info.init_selfdep_validate ( self.selfdeps )
               or self.optional_selfdeps
            ):
               # selfdep reduction is required before ebuild creation can
               # proceed
               self.paused  = True
               self._resume = self._run_create
               self.logger.debug ( "paused - waiting for selfdep validation" )
               return True
            else:
               return self._run_create ( stats )
         else:
            stats.pkg_fail.inc_details ( "unresolved_deps" )
            return False
   # --- end of _run_prepare (...) ---

   def _run_create ( self, stats ):
      self.status    = 3
      p_info         = self.package_info
      dep_resolution = self.dep_resolution
      desc           = self.package_info ['desc_data']

      if p_info.end_selfdep_validate():
         ebuild      = ebuilder.Ebuilder()
         evars_dep   = dep_resolution.get_evars()
         evars_extra = p_info.get_evars()

         if evars_extra:
            ebuild.use ( *evars_extra )

            #evars_overridden = tuple ( ebuild.get_names() )
            # for k in evars_dep <other evars...>:
            #    if k.name not in evars_overridden: ebuild.use ( k )
         #else:
         #   ...

         # add *DEPEND to the ebuild
         ebuild.use_list ( evars_dep )

         # IUSE
         if dep_resolution.has_suggests:
            rsuggests = ebuild.get ( 'R_SUGGESTS' )
            self.use_expand_flag_names = set ( rsuggests.get_flag_names() )
            ebuild.use ( evars.IUSE ( sorted ( rsuggests.get_flags() ) ) )
#         else:
#            ebuild.use ( evars.IUSE() )

         # DESCRIPTION
         # use either Title or Description for DESCRIPTION=
         # (Title preferred 'cause it should be shorter)
         if 'Title' in desc:
            ebuild.use ( evars.DESCRIPTION ( desc ['Title'] ) )

         elif 'Description' in desc:
            ebuild.use ( evars.DESCRIPTION ( desc ['Description'] ) )

         elif FALLBACK_DESCRIPTION is not None:
            ebuild.use ( FALLBACK_DESCRIPTION )

         # SRC_URI
         ebuild.use ( evars.SRC_URI (
            src_uri      = p_info ['SRC_URI'],
            src_uri_dest = p_info.get ( "src_uri_dest", do_fallback=True )
         ) )

         # LICENSE (optional)
         if 'LICENSE' not in ebuild:
            license_str = desc.get ( 'License' )
            if license_str:
               ebuild.use ( evars.LICENSE ( license_str ) )

         # HOMEPAGE (optional)
         if 'HOMEPAGE' not in ebuild:
            homepage_str = desc.get ( 'Homepage' )
            if homepage_str:
               ebuild.use ( evars.HOMEPAGE ( homepage_str ) )

         if 'KEYWORDS' not in ebuild:
            ebuild.use ( evars.KEYWORDS ( "~amd64 ~x64-macos ~arm64-macos" ) )

         #ebuild_text = ebuild.to_str()
         ## FIXME: debug rstrip()
         ebuild_text = ebuild.to_str().rstrip()

         p_info.update_now (
            ebuild=ebuild_text,
            has_suggests=dep_resolution.has_suggests,
         )

         self.status = 0
         return True
      elif (
         hasattr ( self, 'selfdeps' ) or hasattr ( self, 'optional_selfdeps' )
      ):
         self.logger.debug ( "selfdep validation failed." )
         if hasattr ( self, 'selfdeps' ):
            for selfdep in self.selfdeps:
               self.logger.debug (
                  "selfdep {}: {}".format (
                     selfdep.dep, "OK" if selfdep.is_valid() else "FAIL"
                  )
               )
         if hasattr ( self, 'optional_selfdeps' ):
            for selfdep in self.optional_selfdeps:
               self.logger.debug (
                  "optional selfdep {}: {}".format (
                     selfdep.dep, "OK" if selfdep.is_valid() else "FAIL"
                  )
               )

         stats.pkg_fail.inc_details ( "bad_selfdeps" )
         return False
      else:
         raise AssertionError (
            "selfdep validation must not fail if no selfdeps are present!"
         )
   # --- end of _run_create (...) ---

# --- end of EbuildCreation ---
