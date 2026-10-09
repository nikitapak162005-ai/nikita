import os
import re


LOG_FILES = [
    "logs/client-1.log",
    "logs/client-2.log",
    "logs/client-3.log",
    "logs/replica-A.log",
]

OUTPUT_FILE = "logs/trace_excerpt.txt"
MAX_LINES = 30


def get_lamport_time(line):
    match = re.search(r"\bL=(\d+)", line)

    if match:
        return int(match.group(1))

    return 0


def main():
    all_lines = []

    for file_name in LOG_FILES:
        if not os.path.exists(file_name):
            print(f"Missing file: {file_name}")
            continue

        with open(file_name, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if line:
                    all_lines.append(line)

    if not all_lines:
        print("No log lines found.")
        return

    # Sort by the Lamport value shown for each event.
    all_lines.sort(key=get_lamport_time)

    excerpt = all_lines[:MAX_LINES]

    os.makedirs("logs", exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        for line in excerpt:
            file.write(line + "\n")

    print(f"Created {OUTPUT_FILE}")
    print(f"Lines written: {len(excerpt)}")


if __name__ == "__main__":
    main()