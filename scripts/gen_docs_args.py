import subprocess

import mkdocs_gen_files  # type: ignore

process = subprocess.Popen(
    ["python", "mosec/args.py", "--help"], stdout=subprocess.PIPE
)
stdout = process.communicate()[0].decode()
stdout = stdout.replace("args.py", "python your_model_server.py")
mkstr = f"```text\n{stdout}\n```"

with mkdocs_gen_files.open("argument.md", "w") as f:
    print(mkstr, file=f)
