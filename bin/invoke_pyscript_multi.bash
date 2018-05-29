#!/bin/bash
# similar to invoke_pyscript.bash, but runs the python script once for
# each python implementation (PYTHON_IMPL).
#
# Also contains some script-specific code,
# e.g. creates a R-overlay.conf.tests file.
#

: ${PYTHON_IMPL:="python3"}

readonly SCRIPT=$(readlink -f "${BASH_SOURCE[0]?}")
readonly SCRIPT_NAME="${BASH_SOURCE[0]##*/}"
readonly SCRIPT_DIR="${SCRIPT%/*}"

readonly PRJROOT="${SCRIPT_DIR%/*}"
readonly PYSCRIPT="${SCRIPT_DIR}/py/${SCRIPT_NAME%.*}.py"

readonly CONFIG_FILE="${PRJROOT}/R-overlay.conf"

export ROVERLAY_PRJROOT="${PRJROOT}"
export PYTHONPATH="${PRJROOT}${PYTHONPATH:+:}${PYTHONPATH}"


cd "${PRJROOT}" || exit


[[ -e "${CONFIG_FILE}.tests" ]] || ln -vs -- "${CONFIG_FILE}"{,.tests} || exit 2

for _py in ${PYTHON_IMPL}; do
   if which "${_py}" 1>/dev/null 2>/dev/null; then
      echo "Running ${PYSCRIPT##*/} with PYTHON=${_py}"
      "${_py}" "${PYSCRIPT}" || exit
   else
      echo "PYTHON=${_py} not found." 1>&2
   fi
done
