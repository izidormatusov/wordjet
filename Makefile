DIST_TARGET := wordjet.tar.gz

.PHONY: dist clean

dist:
	pipenv requirements > requirements.txt
	tar czvf $(DIST_TARGET) *.py requirements.txt static/ templates/ dictionary.txt

clean:
	rm -f $(TARGET) $(DIST_TARGET) requirements.txt
