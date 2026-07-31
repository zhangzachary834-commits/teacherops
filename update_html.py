import glob

font_link = '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">\n'

for path in glob.glob("web/*.html"):
    with open(path, "r") as f:
        content = f.read()
    
    if "fonts.googleapis.com" not in content:
        # Find the end of head
        if "</head>" in content:
            content = content.replace("</head>", f"  {font_link}</head>")
            with open(path, "w") as f:
                f.write(content)
            print(f"Updated {path}")
