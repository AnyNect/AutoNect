from src.parser.commands import extract_commands

sample = """
Here is something.
```command
sudo apt update
sudo apt upgrade -y
```
And another one:
```command
cat <<'EOF' > test.sh
echo "hello"
EOF
```
"""

commands = extract_commands(sample)
for i, cmd in enumerate(commands, 1):
    print(f"--- Command {i} ---")
    print(cmd["code"])
    print()