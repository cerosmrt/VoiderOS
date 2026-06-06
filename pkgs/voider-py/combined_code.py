import os

output_file = "combined_code.txt"
excluded_files = {
    "build_installer.py",
    "combined_py.py",
    "interface.py",
    "nuitka_build_installer.py",
    "realtime_effects.py",
    "test.py",
    "test_circular.py",
}

included_files = []

with open(output_file, "w", encoding="utf-8") as outfile:
    for root, dirs, files in os.walk("."):
        # Ignorar carpetas de cache y builds
        dirs[:] = [d for d in dirs if d not in {"__pycache__", "builds", ".git", "venv", "venv_clean"}]
        
        for file in sorted(files):
            if file.endswith(".py") and file not in excluded_files:
                filepath = os.path.join(root, file)
                included_files.append(filepath)
                with open(filepath, "r", encoding="utf-8") as infile:
                    outfile.write(f"\n\n# --- {filepath} ---\n")
                    outfile.write(infile.read())

print(f"Combined .py files into '{output_file}'")
print("Archivos incluidos:")
for f in included_files:
    print(f" - {f}")