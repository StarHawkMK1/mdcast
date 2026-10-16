import re, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
s = z.read("Contents/section0.xml").decode("utf-8")
s = re.sub(r"<hp:secPr.*?</hp:secPr>", "<SECPR/>", s, flags=re.S)
s = re.sub(r"<hp:linesegarray>.*?</hp:linesegarray>", "", s, flags=re.S)
s = s[s.find("<hp:p "):]
print(s)
