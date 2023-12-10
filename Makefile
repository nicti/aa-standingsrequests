appname = standingsrequests
package = standingsrequests
pipname = aa-standingsrequests

help:
	@echo "Makefile for $(appname)"

makemessages:
	cd $(package) && \
	django-admin makemessages \
		-l de \
		-l en \
		-l es \
		-l fr_FR \
		-l it_IT \
		-l ja \
		-l ko_KR \
		-l ru \
		-l uk \
		-l zh_Hans \
		--keep-pot \
		--ignore 'build/*'

tx_push:
	tx push --source

tx_pull:
	tx pull -f

compilemessages:
	cd $(package) && \
	django-admin compilemessages \
		-l de \
		-l en \
		-l es \
		-l fr_FR \
		-l it_IT \
		-l ja \
		-l ko_KR \
		-l ru \
		-l uk \
		-l zh_Hans

coverage:
	coverage run ../myauth/manage.py test $(appname) --keepdb --failfast && coverage html && coverage report -m

pylint:
	pylint --load-plugins pylint_django $(package)

check_complexity:
	flake8 $(package) --max-complexity=10

flake8:
	flake8 $(package) --count

graph_models:
	python ../myauth/manage.py graph_models $(appname) -X AbstractContact --arrow-shape normal -o $(pipname).png
