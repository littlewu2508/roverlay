# R overlay -- simple dependency rules
# -*- coding: utf-8 -*-
# Copyright (C) 2012 André Erdmann <dywi@mailerd.de>
# Distributed under the terms of the GNU General Public License;
# either version 2 of the License, or (at your option) any later version.

"""simple dependency rules

This module provides 4 simple dependency rules classes
* SimpleDependencyRule
* SimpleIgnoreDependencyRule
* SimpleFuzzyDependencyRule
* SimpleFuzzyIgnoreDependencyRule

(TODO NOTE: could describe rule matching here)
"""

__all__ = (
   'SimpleIgnoreDependencyRule', 'SimpleDependencyRule',
   'SimpleFuzzyDependencyRule', 'SimpleFuzzyIgnoreDependencyRule'
)


import roverlay.strutil
import roverlay.depres.depenv


from roverlay.depres.simpledeprule.util import \
   RuleFileSyntaxError, get_slot_restrict, get_slot_parser

from roverlay.depres.simpledeprule.abstractrules import \
   SimpleRule, FuzzySimpleRule




class RuleConstructor ( object ):

   def __init__ ( self, eapi ):
      ##self.eapi = eapi

      self.kw_ignore       = SimpleIgnoreDependencyRule.RULE_PREFIX
      self.kw_fuzzy        = SimpleFuzzyDependencyRule.RULE_PREFIX
      self.kw_fuzzy_ignore = SimpleFuzzyIgnoreDependencyRule.RULE_PREFIX
   # --- end of __init__ (...) ---

   def lookup ( self, keyworded_str ):
      get_kwless = lambda : keyworded_str[1:].lstrip() or None

      kw = keyworded_str[0]
      if kw == self.kw_ignore:
         return ( SimpleIgnoreDependencyRule, get_kwless(), {} )
      elif kw == self.kw_fuzzy_ignore:
         return ( SimpleFuzzyIgnoreDependencyRule, get_kwless(), {} )
      elif kw == self.kw_fuzzy:
         ## syntax
         ## ~<cat>/<pkg>[:[<slot option>]]*
         ##  where slot option is any of
         ##  * slot restrict (range, list)
         ##  * "with version", "open" ("*" and "=" slot operators)
         ##  * relevant version parts ("1.2.3.4" => "1" if 1, "1.2" if 2, ...)
         ##  * relevant subslot version parts ("1.2.3.4" => <SLOT>/<SUBSLOT?>)
         ##  * slot operator ("=")

         kwless          = get_kwless()
         line_components = kwless.split ( ':' )

         if len ( line_components ) < 2:
            # non-slot fuzzy rule
            return ( SimpleFuzzyDependencyRule, kwless, {} )
         else:
            kwargs = dict()
            lc_iter = iter ( line_components )
            # drop first item as it's the resolving string and not an option
            next ( lc_iter )
            for opt_str in lc_iter:
               opt, has_value, value = opt_str.partition ( '=' )

               if not opt_str:
                  # empty
                  pass
               elif opt == 'default':
                  kwargs ['slot_mode'] = 0

               elif opt == 'with_version' or opt == '+v':
                  kwargs ['slot_mode'] = 1

               elif opt == 'open':
                  kwargs ['slot_mode'] = 2

               elif ( opt == 'restrict' or opt == 'r' ) and value:
                  kwargs ['slot_restrict'] = get_slot_restrict ( value )

               elif ( opt == 'slotparts' or opt == 's' ) and value:
                  kwargs ['slotparts'] = get_slot_parser ( value )

               elif ( opt == 'subslotparts' or opt == '/' ) and value:
                  kwargs ['subslotparts'] = get_slot_parser ( value )

               elif opt_str[0] == '/' and not has_value:
                  kwargs ['subslotparts'] = get_slot_parser ( opt_str[1:] )

#               elif opt == 'operator' and value:
#                  # unsafe, could be used to inject "$(rm -rf /)" etc.
#                  kwargs ['slot_operator'] = value

               elif opt == 'wide_match':
                  if not has_value:
                     kwargs ['allow_wide_match'] = True
                  else:
                     kwargs ['allow_wide_match'] = bool (
                        roverlay.strutil.str_to_bool ( value )
                     )

               elif opt == '*':
                  kwargs ['slot_operator'] = '*'

               elif not opt and has_value:
                  # "="
                  kwargs ['slot_operator'] = '='
                  pass

               else:
                  raise RuleFileSyntaxError (
                     "cannot parse option {!r} from {!r}".format (
                        opt_str, kwless
                     )
                  )
            # -- end for lc_iter

            if (
               kwargs.get ( 'slot_operator' ) == '*'
               and kwargs.get ( 'slot_mode' ) != 2
            ):
               raise RuleFileSyntaxError (
                  "The '*' slot operator needs an 'open' rule."
               )
            else:
               return (
                  SimpleFuzzySlotDependencyRule, line_components[0], kwargs
               )
         # -- end if line_components

      else:
         return ( SimpleDependencyRule, keyworded_str, {} )
   # --- end of lookup (...) ---

# --- end of RuleConstructor ---

class SimpleIgnoreDependencyRule ( SimpleRule ):

   RULE_PREFIX = '!'

   def __init__ ( self, priority=80, resolving_package=None, **kw ):
      super ( SimpleIgnoreDependencyRule, self ) . __init__ (
         logger_name = 'IGNORE_DEPS',
         resolving_package=None,
         priority=80,
         **kw
      )
# --- end of SimpleIgnoreDependencyRule ---


class SimpleDependencyRule ( SimpleRule ):

   def __init__ ( self, priority=70, resolving_package=None, **kw ):
      """Initializes a SimpleDependencyRule. This is
      a SimpleIgnoreDependencyRule extended by a portage package string.

      arguments:
      * resolving package --
      * dep_str --
      * priority --
      """
      super ( SimpleDependencyRule, self ) . __init__ (
         priority=priority,
         logger_name=resolving_package,
         resolving_package=resolving_package,
         **kw
      )
   # --- end of __init__ (...) ---

# --- end of SimpleDependencyRule ---


class SimpleFuzzyIgnoreDependencyRule ( FuzzySimpleRule ):

   RULE_PREFIX = '%'

   def __init__ ( self, priority=81, resolving_package=None, **kw ):
      super ( SimpleFuzzyIgnoreDependencyRule, self ) . __init__ (
         priority=priority,
         resolving_package=resolving_package,
         logger_name = 'FUZZY.IGNORE_DEPS',
         **kw
      )

   def handle_version_relative_match ( self, *args, **kwargs ):
      raise Exception ( "should-be unreachable code" )
   # --- end of handle_version_relative_match (...) ---

# --- end of SimpleFuzzyIgnoreDependencyRule ---


class SimpleFuzzyDependencyRule ( FuzzySimpleRule ):

   RULE_PREFIX = '~'

   def __init__ ( self, priority=72, resolving_package=None, **kw ):
      super ( SimpleFuzzyDependencyRule, self ) . __init__ (
         priority=priority,
         resolving_package=resolving_package,
         logger_name = 'FUZZY.' + resolving_package,
         **kw
      )
   # --- end of __init__ (...) ---

   def handle_version_relative_match ( self, dep_env, fuzzy ):
      ver_pkg  = self.resolving_package + '-' + fuzzy ['version']
      vmod_str = fuzzy ['version_modifier']
      vmod     = fuzzy ['vmod']

      #if vmod & dep_env.VMOD_NOT:
      if vmod == dep_env.VMOD_NE:
         # package matches, but specific version is forbidden
         # ( !<package>-<specific verion> <package> )
         return "( !={vres} {res} )".format (
            vres=ver_pkg, res=self.resolving_package
         )
      else:
         # std vmod: >=, <=, =, <, >
         return vmod_str + ver_pkg
   # --- end of handle_version_relative_match (...) ---

# --- end of SimpleFuzzyDependencyRule ---


class SimpleFuzzySlotDependencyRule ( FuzzySimpleRule ):
   # 2 slot variants
   # "slot only": resolve dep_str as <cat>/<pkg>:<slot>
   # "combined": resolve dep_str as <vmod><cat>/<pkg>-<ver>:<slot>

#   FMT_DICT = {
#      'slot' : '{slot}',
#   }

   #RULE_PREFIX        = '~'
   RULE_PREFIX         = SimpleFuzzyDependencyRule.RULE_PREFIX

   # version relation operators that should never be matched in slot dep rules
   #  (bitmask)
   VMOD_BASE_DENY_MASK = roverlay.depres.depenv.DepEnv.VMOD_NOT

   # operators that should not be matched in nonwide mode (bitmask)
   #  - in addition to the base mask -
   VMOD_WIDE_DENY_MASK = roverlay.depres.depenv.DepEnv.VMOD_GT


   def __init__ ( self,
      priority          = 71,
      resolving_package = None,
      slot_mode         = None,
      slot_restrict     = None,
      slotparts         = None,
      subslotparts      = None,
      slot_operator     = None,
      allow_wide_match  = None,
      **kw
   ):
      super ( SimpleFuzzySlotDependencyRule, self ) . __init__ (
         priority=priority,
         resolving_package = resolving_package,
         logger_name       = 'FUZZY_SLOT.' + resolving_package,
         **kw
      )

      self.mode             = 0 if slot_mode is None else slot_mode
      self.slot_restrict    = slot_restrict
      self.slot_operator    = slot_operator
      self.slotparts        = (
         get_slot_parser ("0") if slotparts is None else slotparts
      )
      self.subslotparts     = subslotparts
      self.allow_wide_match = allow_wide_match
      self.vmod_mask        = self.VMOD_BASE_DENY_MASK
      if not allow_wide_match:
         self.vmod_mask |= self.VMOD_WIDE_DENY_MASK

      if self.mode == 0:
         # "default"
         self._resolving_fmt = self.resolving_package + ':{slot}'
         if self.slot_operator:
            self._resolving_fmt += self.slot_operator

      elif self.mode == 1:
         # "with version"
         self._resolving_fmt = (
            '{vmod}' + self.resolving_package + '-{version}:{slot}'
         )
         if self.slot_operator:
            self._resolving_fmt += self.slot_operator

      elif self.mode == 2:
         # "open" slot
         if not self.slot_operator:
            self.slot_operator = '='

         del self.slot_restrict

         self._orig_resolving_package = self.resolving_package
         self.resolving_package += ':' + self.slot_operator
      else:
         raise Exception (
            "unknown fuzzy slot rule mode {}".format ( self.mode )
         )



      if self.is_selfdep:
         raise NotImplementedError ( "fuzzy slot rule must not be a selfdep." )
   # --- end of __init__ (...) ---

   def noexport ( self ):
      del self.slot_operator
      del self.allow_wide_match

      if self.slot_restrict:
         self.slot_restrict.noexport()
   # --- end of noexport (...) ---

   def get_resolving_str ( self ):
      def gen_opts():
         if self.allow_wide_match:
            yield "wide_match"

#         yield "vmod_mask={:#x}".format (
#            self.vmod_mask & ~self.VMOD_BASE_DENY_MASK
#         )

         if self.mode == 2:
            yield "open"
         else:
            if self.mode == 1:
               yield "with_version"

            if self.slot_restrict:
               yield "restrict=" + str ( self.slot_restrict )

            if self.slotparts and (
               not hasattr ( self.slotparts, '_index' )
               or  self.slotparts._index != 0
            ):
               yield "s=" + str ( self.slotparts )

            if self.subslotparts:
               yield "/" + str ( self.subslotparts )
         # -- end if
         if self.slot_operator:
            yield self.slot_operator

      return "{prefix}{resolv}:{opts}".format (
         prefix = self.RULE_PREFIX,
         resolv = (
            self._orig_resolving_package
            if hasattr ( self, '_orig_resolving_package' )
            else self.resolving_package
         ),
         opts   = ':'.join ( gen_opts() )
      )
   # --- end of get_resolving_str (...) ---

   def handle_version_relative_match ( self, dep_env, fuzzy ):
      def get_slotted_result ( dep_env, fuzzy, vmod ):
         slot_str  = None
         vslot_str = None
         slot      = self.slotparts.get_slot ( fuzzy )

         if slot is not None:
            if self.subslotparts:
               subslot = self.subslotparts.get_slot ( fuzzy )
               if subslot is not None:
                  slot_str  = slot + '/' + subslot
                  vslot_str = (
                     self.slotparts.calculate_slot ( fuzzy, slot )
                     + '/'
                     + self.subslotparts.calculate_slot ( fuzzy, subslot )
                  )
            else:
               vslot_str = self.slotparts.calculate_slot ( fuzzy, slot )
               slot_str  = slot

            if slot_str and (
               not self.slot_restrict
               or self.slot_restrict.accepts ( vslot_str )
            ):
               return self._resolving_fmt.format (
                  slot    = slot_str,
                  version = fuzzy ['version'],
                  vmod    = fuzzy ['version_modifier']
               )
            # -- end if <accepted slot>
         # -- end if <have slot>

         # explicit return
         return False
      # --- end of get_slot_result (...) ---

      res  = False
      vmod = fuzzy ['vmod']


      if vmod & self.vmod_mask:
         # can never be resolved as slot(ted) dep
         return False

##    MAYBE TODO
##    elif self.ident and dep_env.want_slotres_override(self.ident):
###        ^^^^^^^^^^?            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^?
##       want_slot_res, ... = dep_env.get_slotres_override(self.ident,...)
###                                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^?
##       if not want_slot_res:
##          return False
##       elif ...:
##          ...
##

      # else might be resolvable as slot(ted) dep
      elif self.mode == 2:
         return self.resolving_package
      elif vmod & dep_env.VMOD_EQ:
         return get_slotted_result ( dep_env, fuzzy, vmod )
      else:
         return False
      # -- end if <vmod>

   # --- end of handle_version_relative_match (...) ---
