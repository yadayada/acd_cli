deb: 
	fpm -s python -t deb requests-toolbelt
	fpm -s python -t deb --python-pip /usr/bin/pip3 --python-bin /usr/bin/python3 ../setup.py

rpm:
	fpm -s python -t rpm requests-toolbelt
	fpm -s python -t rpm --python-pip /usr/bin/pip3 --python-bin /usr/bin/python3 ../setup.py
