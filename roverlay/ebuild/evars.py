# R overlay -- ebuild creation, ebuild variables
# -*- coding: utf-8 -*-
# Copyright (C) 2012, 2013 André Erdmann <dywi@mailerd.de>
# Distributed under the terms of the GNU General Public License;
# either version 2 of the License, or (at your option) any later version.

"""ebuild variables

This module implements all used ebuild variables (e.g. DEPEND, SRC_URI)
as classes.
These variables have different properties, e.g. DESCRIPTION's string is cut
after n (50) chars, RDEPEND is only printed if not empty and MISSINGDEPS
is printed as bash array.
"""

__all__ = [ 'DEPEND', 'DESCRIPTION', 'IUSE', 'MISSINGDEPS',
   'RDEPEND', 'R_SUGGESTS_USE_EXPAND', 'SRC_URI', 'KEYWORDS',
]

import collections
import re

import roverlay.strutil

import roverlay.ebuild.abstractcomponents

from roverlay.ebuild.abstractcomponents import ListValue, get_value_str

RSUGGESTS_NAME = 'R_SUGGESTS'

# ignoring style guide here (camel case, ...)

class DependListValue ( roverlay.ebuild.abstractcomponents.ListValue ):

   def add ( self, deps ):
      if deps:
         if isinstance ( deps, str ):
            self.value.append ( deps )
         else:
            for item in deps:
               self.value.append ( item.dep )
   # --- end of add (...) ---

# --- end of DependListValue ---

class DependencyVariable ( roverlay.ebuild.abstractcomponents.EbuildVar ):
   #DEFAULT_PRIORITY = 140

   def __init__ ( self, deps, empty_value=None, **kw ):
      cls = self.__class__
      super ( DependencyVariable, self ).__init__ (
         name            = cls.__name__,
         value           = DependListValue ( deps, empty_value=empty_value ),
         priority        = cls.DEFAULT_PRIORITY,
         param_expansion = True,
         #ignore **kw
      )
      if empty_value is not None:
         self.print_empty_var = True
   # --- end of __init__ (...) ---

# --- end of DependencyVariable ---


class DEPEND ( DependencyVariable ):
   """A DEPEND="..." statement."""
   DEFAULT_PRIORITY = 150
# --- end of DEPEND ---

class RDEPEND ( DependencyVariable ):
   """A RDEPEND="..." statement."""
   DEFAULT_PRIORITY = 160

   def __init__ ( self, deps, using_suggests=False, **kwargs ):
      super ( RDEPEND, self ).__init__ (
         deps, empty_value="${DEPEND-}", **kwargs
      )
      if using_suggests:
         self.enable_suggests()
   # --- end of __init__ (...) ---


   def enable_suggests ( self ):
      """Adds the optional R_SUGGESTS dependencies to RDEPEND."""
      self.add_value ( '${' + RSUGGESTS_NAME + '-}' )
   # --- end of enable_suggests (...) ---

# --- end of RDEPEND ---


class UseExpandListValue (
   roverlay.ebuild.abstractcomponents.AbstractListValue
):
   """List value that represents USE_EXPAND-conditional depend atoms."""

   RE_USENAME = re.compile (
      (
         '(?P<prefix>.*[/])?'
         '(?P<pn>[^\[]*)(\[(?P<use>[^\]]*)\])?(?P<pvr>[-][0-9].*([-]r[0-9]+)?)?'
      )
   )

   def __init__ (
      self, basename, deps, alias_map=None, indent_level=1, **kw
   ):
      super ( UseExpandListValue, self ).__init__ (
         indent_level = indent_level,
         empty_value  = None,
         bash_array   = False,
         **kw
      )
      self.insert_leading_newline = True
      # dict { <internal flag name> => <overlay flag name> }
      self.alias_map              = alias_map or None
      self.basename               = basename.rstrip ( '_' ).lower()
      self.sort_flags             = True

      # dict { <overlay flag name> => <list [dep...]> }
      #self.depdict = dict()
      self.set_value ( deps )
   # --- end of __init__ (...) ---

   def _get_depstr_key ( self, dep ):
      # tries to get the use flag name from dep.dep
      # str(dep) == dep.dep
      match = self.__class__.RE_USENAME.match ( dep.dep )
      if match:
         return self._get_use_key (
            ( match.group ( "use" ) or match.group ( "pn" ) )
         )
      else:
         raise ValueError (
            "depstr {!r} cannot be parsed".format ( dep.dep )
         )
   # --- end of _get_depstr_key (...) ---

   def _get_use_key ( self, orig_key ):
      key_low = orig_key.lower()
      if self.alias_map:
         return self.alias_map.get ( key_low, key_low ).lower()
      else:
         return key_low
   # --- end of _get_use_key (...) ---

   def set_value ( self, deps ):
      self.depdict = dict()
      if deps: self.add ( deps )
   # --- end of set_value (...) ---

   def add ( self, deps ):
      assert not isinstance ( deps, str )

      for item in deps:
         if hasattr ( item, '__iter__' ) and not isinstance ( item, str ):
            key = self._get_use_key ( str ( item [0] ) )
            val = item [1].dep
         elif hasattr ( item, 'package' ):
            key = self._get_use_key ( item.package )
            val = item.dep
         else:
            key = self._get_depstr_key ( item )
            val = item.dep
         # -- end if;

         vref = self.depdict.get ( key, None )
         if vref is None:
            self.depdict [key] = [ val ]
         else:
            vref.append ( val )
         # -- end if;
   # --- end of add (...) ---

   def get_flag_names ( self ):
      return self.depdict.keys()
   # --- end of get_flags (...) --

   def get_flags ( self ):
      prefix = self.basename + '_'
      for flagname in self.depdict.keys():
         yield prefix + flagname
   # --- end of get_flags (...) ---

   def __len__ ( self ):
      return (
         self.depcount if hasattr ( self, 'depcount' )
         else len ( self.depdict )
      )
   # --- end of __len__ (...) ---

   def cleanup ( self ):
      depcount = 0
      delkeys  = set()
      for k, v in self.depdict.items():
         if v:
            depcount += len ( v )
         else:
            delkeys.add ( k )
      # -- end for

      for k in delkeys:
         del self.depdict [k]

      self.depcount = depcount
   # --- end of cleanup (...) ---

   def join_value_str ( self, join_str, quoted=False ):
      # get_value_str() not strictly necessary here,
      # but it catches incorrect handling of config options/values
      #
      if self.sort_flags:
         return join_str.join (
            get_value_str (
               "{basename}_{flag}? ( {deps} )".format (
                  basename=self.basename, flag=k, deps=' '.join ( v )
               )
            ) for k, v in sorted (
               self.depdict.items(), key=( lambda item : item[0] )
            )
         )
      else:
         return join_str.join (
            get_value_str (
               "{basename}_{flag}? ( {deps} )".format (
                  basename=self.basename, flag=k, deps=' '.join ( v )
               )
            ) for k, v in self.depdict.items()
         )
   # --- end of join_value_str (...) ---

   def to_str ( self ):
      self.cleanup()
      return self._get_sh_list_str()
   # --- end of to_str (...) ---

# --- end of UseExpandListValue ---

class LICENSE ( roverlay.ebuild.abstractcomponents.EbuildVar ):
   def __init__ ( self, license_str ):
      super ( LICENSE, self ).__init__ (
         name            = 'LICENSE',
         value           = license_str,
         priority        = 100,
         param_expansion = False,
      )
   # --- end of __init__ (...) ---
# --- end of LICENSE ---


class HOMEPAGE ( roverlay.ebuild.abstractcomponents.EbuildVar ):
   def __init__ ( self, homepage ):
      super ( HOMEPAGE, self ).__init__ (
         name            = 'HOMEPAGE',
         value           = homepage,
         priority        = 95,
         param_expansion = False,
      )
   # --- end of __init__ (...) ---
# --- end of HOMEPAGE ---


class DESCRIPTION ( roverlay.ebuild.abstractcomponents.EbuildVar ):
   """A DESCRIPTION="..." statement."""

   SEE_METADATA = '... (see metadata)'

   def __init__ ( self, description, maxlen=None ):
      """A DESCRIPTION="..." statement. Long values will be truncated.

      arguments:
      * description -- description text
      * maxlen      -- maximum value length (>0, defaults to 50 chars)
      """
      assert maxlen is None or maxlen > 0

      super ( DESCRIPTION, self ) . __init__ (
         name='DESCRIPTION',
         value=description,
         priority=80, param_expansion=False
      )
      self.maxlen = maxlen or 50
   # --- end of __init__ (...) ---

   def _transform_value_str ( self, _str ):
      return roverlay.strutil.shorten_str (
         _str,
         self.maxlen,
         self.SEE_METADATA
      )
   # --- end of _transform_value_str (...) ---


class KEYWORDS ( roverlay.ebuild.abstractcomponents.EbuildVar ):
   """A KEYWORDS="amd64 -x86 ..." statement."""
   def __init__ ( self, keywords ):
      super ( KEYWORDS, self ).__init__ (
         name=self.__class__.__name__,
         value=keywords,
         priority=80
      )
   # --- end of __init__ (...) ---


class SRC_URI_ListValue ( roverlay.ebuild.abstractcomponents.ListValue ):
   """List value that represents SRC_URI entries."""

   def _accept_value ( self, value ): raise NotImplementedError()

   def add ( self, value ):
      """Adds/Appends a value."""
      if value [0]:
         self.value.append ( value )
      else:
         raise ValueError ( value )
   # --- end of add (...) ---

   def join_value_str ( self, join_str, quoted=False ):
      return join_str.join (
         get_value_str (
            ( "{} -> {}".format ( v[0], v[1] ) if v[1] else str ( v[0] ) ),
            quote_char=( "'" if quoted else None )
         ) for v in self.value
      )
   # --- end of join_value_str (...) ---


class SRC_URI ( roverlay.ebuild.abstractcomponents.EbuildVar ):
   """A SRC_URI="..." statement."""
   def __init__ ( self, src_uri, src_uri_dest ):
      super ( SRC_URI, self ) . __init__ (
         name     = 'SRC_URI',
         value    = SRC_URI_ListValue ( value=( src_uri, src_uri_dest ) ),
         priority = 90
      )

   def _empty_str ( self ):
      """Called if this SRC_URI evar has no uri stored."""
      return 'SRC_URI=""\nRESTRICT="fetch"'
# --- end of SRC_URI ---

class IUSE ( roverlay.ebuild.abstractcomponents.EbuildVar ):
   """An IUSE="..." statement."""

   def __init__ ( self, use_flags=None ):
      """An IUSE="..." statement.

      arguments:
      * use_flags      -- IUSE value
      * using_suggests -- if True: enable R_Suggests USE flag
      """
      super ( IUSE, self ) . __init__ (
         name='IUSE',
         value=ListValue ( use_flags, empty_value='${IUSE-}' ),
         priority=130,
         param_expansion=True
      )
      self.value.single_line = True

      # bind text wrapper
      self._transform_value_str = self.fold_value
   # --- end of __init__ (...) ---
# --- end of IUSE ---

class R_SUGGESTS_USE_EXPAND ( roverlay.ebuild.abstractcomponents.EbuildVar ):
   """A R_SUGGESTS="..." statement with USE_EXPAND support."""

   def __init__ ( self, use_expand_name, deps, use_expand_map=None, **kw ):
      super ( R_SUGGESTS_USE_EXPAND, self ).__init__ (
         name=RSUGGESTS_NAME,
         value=UseExpandListValue (
            basename=use_expand_name, deps=deps, alias_map=use_expand_map
         ),
         priority=140,
      )
   # --- end of __init__ (...) ---

   def get_use_expand_name ( self ):
      return self.value.basename.upper()
   # --- end of get_use_expand_name (...) ---

   def get_flag_names ( self, *args, **kwargs ):
      return self.value.get_flag_names ( *args, **kwargs )
   # --- end of get_flag_names (...) ---

   def get_flags ( self, *args, **kwargs ):
      return self.value.get_flags ( *args, **kwargs )
   # --- end of get_flags (...) ---


class MISSINGDEPS ( roverlay.ebuild.abstractcomponents.EbuildVar ):
   def __init__ ( self, missing_deps, do_sort=False, **kw ):
      super ( MISSINGDEPS, self ) . __init__ (
         name            = '_UNRESOLVED_PACKAGES',
         value           = ListValue (
            (
               missing_deps if not do_sort
               else sorted ( missing_deps, key=lambda s : s.lower() )
            ),
            bash_array=True
         ),
         priority        = 200,
         param_expansion = None,
      )
