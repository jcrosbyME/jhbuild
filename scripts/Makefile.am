EXTRA_DIST = hg-update.py jhbuild.in debian-python2-postinstall-hook.sh

bin_SCRIPTS = jhbuild
CLEANFILES = jhbuild

pkgdata_SCRIPTS = hg-update.py

jhbuild: jhbuild.in
	sed						\
		-e s!\@srcdir\@!$(abs_top_srcdir)!	\
		-e s!\@prefix\@!$(prefix)!		\
		-e s!\@datadir\@!$(datadir)!		\
		-e s!\@pkgdatadir\@!$(pkgdatadir)!	\
		-e s!\@libexecdir\@!$(libexecdir)!	\
		-e s!\@libdir\@!$(libdir)!		\
		-e s!\@pythondir\@!$(pythondir)!	\
		-e s!\@PACKAGE\@!$(PACKAGE)!		\
		-e s!\@VERSION\@!$(VERSION)!		\
		< $< > $@

jhbuild: Makefile

all-local: jhbuild

