# R overlay -- simple dependency rules, abstract rules
# -*- coding: utf-8 -*-
# Copyright (C) 2012 André Erdmann <dywi@mailerd.de>
# Distributed under the terms of the GNU General Public License;
# either version 2 of the License, or (at your option) any later version.

"""implements abstract simple dependency rules"""

__all__ = [ 'FuzzySimpleRule', 'SimpleRule', ]

import logging, re

from roverlay import config
from roverlay.depres import deprule

TMP_LOGGER = logging.getLogger ('simpledeps')

class SimpleRule ( deprule.DependencyRule ):
   """A dependency rule that represents an ignored package in portage."""

   INDENT = 3 * ' '

   def __init__ ( self,
      dep_str=None, priority=80, resolving_package=None,
      is_selfdep=0, logger_name='simple_rule',
      selfdep_package_names=None, finalize=False,
   ):
      """Initializes a SimpleIgnoreDependencyRule.

      arguments:
      * dep_str -- a dependency string that this rule is able to resolve
      * priority -- priority of this rule
      """
      super ( SimpleRule, self ) . __init__ ( priority )

      self.dep_alias               = list()
      self.logger                  = TMP_LOGGER.getChild ( logger_name )
      self.is_selfdep              = int ( is_selfdep or 0 )
      self.resolving_package       = resolving_package
      self.prepare_lowercase_alias = True

      if dep_str is not None:
         self.dep_alias.append ( dep_str )

         if self.is_selfdep:
            # add the actual package name to self.dep_alias
            #  (replace '_' by '.' or use selfdep_package_names)
            #
            #
            # no need to check for duplicates, they get removed
            # in done_reading anyway

            if selfdep_package_names:
               for alias in selfdep_package_names:
                  self.dep_alias.append ( alias )
            ##elif selfdep_package_names is False: ignore
            else:
               actual_name = dep_str.replace ( '_', '.' )
               self.dep_alias.append ( dep_str )
      # -- end if dep_str

      if finalize:
         self.done_reading()
   # --- end of __init__ (...) ---

   def done_reading ( self ):
      self.dep_alias = frozenset ( self.dep_alias )
      if self.prepare_lowercase_alias:
         self.dep_alias_low = frozenset ( x.lower() for x in self.dep_alias )
         temp_set = self.dep_alias_low
         if self.is_selfdep:
            temp_set = ("^{}$".format(x) for x in self.dep_alias_low)
         self.dep_regex = re.compile('|'.join(x for x in temp_set))

   def add_resolved ( self, dep_str ):
      """Adds an dependency string that should be matched by this rule.

      arguments:
      * dep_str --
      """
      self.dep_alias.append ( dep_str )
   # --- end of add_resolved (...) ---

   def _find ( self, dep_str, lowercase ):
      if lowercase:
         if hasattr ( self, 'dep_alias_low' ):
            if self.dep_regex.search(dep_str):
               return True

         elif dep_str in ( alias.lower() for alias in self.dep_alias ):
            return True

      return dep_str in self.dep_alias
   # --- end of _find (...) ---

   def matches ( self, dep_env, lowercase=True ):
      """Returns True if this rule matches the given DepEnv, else False.

      arguments:
      * dep_env --
      * lowercase -- if True: be case-insensitive when iterating over all
                     stored dep_strings
      """

      if self._find (
         dep_env.dep_str_low if lowercase else dep_env.dep_str, lowercase
      ):
         self.logger.debug (
            "matches {dep_str} with score {s} and priority {p}.".format (
               dep_str=dep_env.dep_str, s=self.max_score, p=self.priority
         ) )
         return self.make_result (
            self.resolving_package, self.max_score, dep_env=dep_env
         )

      return None
   # --- end of matches (...) ---

   def noexport ( self ):
      """Removes all variables from this object that are used for string
      creation ("export_rule()") only.
      """
      pass
   # --- end of noexport (...) ---

   def export_rule ( self, with_selfdep_keyword=True ):
      """Generates text lines for this rule that can later be read using
      the SimpleDependencyRuleReader.
      """
      if hasattr ( self, 'get_resolving_str' ):
         resolving = self.get_resolving_str()
      else:
         if self.resolving_package is None:
            resolving = ''
         else:
            resolving = self.resolving_package

            if self.is_selfdep == 2:
               resolving = resolving.rpartition ( '/' ) [2]


         if hasattr ( self.__class__, 'RULE_PREFIX' ):
            resolving = self.__class__.RULE_PREFIX + resolving
      # -- end if;


      if self.is_selfdep == 2:
         yield resolving

      elif self.dep_alias:
         if with_selfdep_keyword and self.is_selfdep == 1:
            yield '@selfdep'

         if len ( self.dep_alias ) == 1:
            yield "{} :: {}".format (
               resolving, next ( iter ( self.dep_alias ) )
            )

         else:
            yield resolving + ' {'
            for alias in self.dep_alias:
               yield self.INDENT + alias
            yield '}'
   # --- end of export_rule (...) ---

   def __str__ ( self ):
      return '\n'.join ( self.export_rule() )
   # --- end of __str__ (...) ---

# --- end of SimpleRule ---


class FuzzySimpleRule ( SimpleRule ):

   # 0 : version-relative, 1 : name only, 2 : std
   FUZZY_SCORE = ( 1250, 1000, 750 )
   max_score   = max ( FUZZY_SCORE )

   def __init__ ( self, *args, **kw ):
      super ( FuzzySimpleRule, self ).__init__ ( *args, **kw )
      self.prepare_lowercase_alias = True
   # --- end of __init__ (...) ---

   def match_prepare ( self, dep_env ):
      if self._find ( dep_env.dep_str_low, lowercase=True ):
         return ( 2, None )

      elif not hasattr ( dep_env, 'fuzzy' ):
         return None

      elif self.resolving_package is None:
         # ignore rule
         for fuzzy in dep_env.fuzzy:
            if self._find ( fuzzy ['name_low'], lowercase=True ):
               return ( 1, fuzzy )
      else:
         for fuzzy in dep_env.fuzzy:
            if self._find ( fuzzy ['name_low'], lowercase=True ):
               return ( 0, fuzzy )
            # -- end if find (=match found)
      # -- end if
      return None
   # --- end of match_prepare (...) ---

   def log_fuzzy_match ( self, dep_env, dep, score, fuzzy ):
      if dep is False:
         return None
      else:
         self.logger.debug (
            'fuzzy-match: {dep_str} resolved as '
            '{dep!r} with score={s}'.format (
               dep_str=dep_env.dep_str, dep=dep, s=score
            )
         )
         return self.make_result ( dep, score, dep_env=dep_env, fuzzy=fuzzy )
   # --- end of log_fuzzy_match (...) ---

   def log_standard_match ( self, dep_env, score ):
      self.logger.debug (
         "matches {dep_str} with score {s} and priority {p}.".format (
            dep_str=dep_env.dep_str, s=score, p=self.priority
         )
      )
      return self.make_result ( self.resolving_package, score )
   # --- end of log_standard_match (...) ---

   def handle_version_relative_match ( self, dep_env, fuzzy ):
      raise NotImplementedError()
   # --- end of handle_version_relative_match (...) ---

   def matches ( self, dep_env ):
      partial_result = self.match_prepare ( dep_env )
      if partial_result is None:
         return None
      else:
         match_type, fuzzy = partial_result
         score = self.FUZZY_SCORE [match_type]
         if match_type == 0:
            # real version-relative match
            return self.log_fuzzy_match (
               dep_env,
               self.handle_version_relative_match ( dep_env, fuzzy ),
               score,
               fuzzy
            )
         elif match_type == 1:
            # name-only match (ignore rule?)
            return self.log_fuzzy_match (
               dep_env, self.resolving_package, score, fuzzy
            )
         else:
            # non-fuzzy match
            return self.log_standard_match ( dep_env, score )
      # -- end if partial_result
   # --- end of matches (...) ---

# --- end of FuzzySimpleRule ---
