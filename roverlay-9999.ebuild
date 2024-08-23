# Copyright 1999-2020 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

EAPI=7

PYTHON_COMPAT=( python3_11 )
PYTHON_REQ_USE="ssl,threads(+),readline(+)"

EGIT_REPO_URI='git://anongit.gentoo.org/proj/R_overlay.git'

DOCS=( examples )
HTML_DOCS=( doc/html/. )

inherit user distutils-r1 git-r3 bash-completion-r1

DESCRIPTION="Automatically generated overlay of R packages"
HOMEPAGE="https://cgit.gentoo.org/proj/R_overlay.git"
SRC_URI=""

LICENSE="GPL-2+"
SLOT="0"
KEYWORDS=""
IUSE="compress-config xz +prebuilt-documentation"

DEPEND="
	dev-python/setuptools[${PYTHON_USEDEP}]
	!prebuilt-documentation? ( >=dev-python/docutils-0.9 )
	compress-config? ( app-arch/bzip2 )"
RDEPEND="
	sys-apps/portage
	dev-python/mako[${PYTHON_USEDEP}]"

pkg_preinst() {
	enewgroup roverlay
}

python_compile_all() {
	use prebuilt-documentation || emake htmldoc
	if use compress-config; then
		einfo "Compressing dependency rules and license map"
		emake X_COMPRESS=bzip2 BUILDDIR="${S}/compressed" compress-config
	fi
}

python_install_all() {
	distutils-r1_python_install_all

	emake BUILDDIR="${S}/compressed" DESTDIR="${D}" \
		BASHCOMPDIR="${D}/$(get_bashcompdir)" \
		COMPRESSED_CONFIG="$(usex compress-config 1 0)" \
		install-nonpy

	insinto /usr/share/roverlay/eclass
	doins files/eclass/R-packages.eclass
	doins -r files/hooks
}

pkg_config() {
	${PN}-setup-interactive || die
}
