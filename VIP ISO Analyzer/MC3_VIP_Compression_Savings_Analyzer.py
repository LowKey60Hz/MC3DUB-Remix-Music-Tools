from pathlib import Path
import json
import zlib
from collections import defaultdict

REPORT = Path("VIP_v11A_Archive_Entry_Report.json")
SOURCE = Path("VIP_v11A_ASSETS_Decompiled")

entries = json.loads(
    REPORT.read_text(encoding="utf-8")
)["all_entries"]

groups = defaultdict(list)

for entry in entries:
    if entry["directory_record"]:
        continue

    if not entry["name"].lower().endswith(".pck"):
        continue

    groups[entry["name"]].append(entry)

print("\n=== VIP v1.1-A PCK COMPRESSION ANALYSIS ===")
print("Unique PCK files:", len(groups))
print("Total PCK archive records:", sum(map(len, groups.values())))

original_total = 0
optimized_total = 0
improved = 0
unchanged = 0
increased = 0
gross_savings = 0
gross_increases = 0
results = []

for index, (name, records) in enumerate(groups.items(), 1):

    # Use the extracted filename exactly as represented
    # in the archive report.
    relative = Path(*name.replace("\\", "/").split("/"))

    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe archive path: {name}")

    path = SOURCE / relative

    data = path.read_bytes()

    compressor = zlib.compressobj(
        level=9,
        method=zlib.DEFLATED,
        wbits=-15
    )

    compressed = compressor.compress(data) + compressor.flush()

    if zlib.decompress(compressed, -15) != data:
        raise RuntimeError(f"Verification failed: {name}")

    for record in records:

        if len(data) != record["full_size"]:
            raise RuntimeError(f"Original size mismatch: {name}")

        old_size = record["stored_size"]

        # Preserve the record's compression status.
        # For uncompressed records, retain the original payload.
        if record["compressed"]:
            new_size = min(old_size, len(compressed))
        else:
            new_size = old_size

        original_total += old_size
        optimized_total += new_size

        if new_size < old_size:
            improved += 1
            gross_savings += old_size - new_size
        elif new_size > old_size:
            increased += 1
            gross_increases += new_size - old_size
        else:
            unchanged += 1

        if new_size < old_size:
            results.append((
                old_size - new_size,
                name,
                old_size,
                new_size
            ))

    if index % 200 == 0:
        print(f"Analyzed {index:,}/{len(groups):,} files")

print("\n=== RESULTS ===")
print("Original stored bytes:", f"{original_total:,}")
print("Optimized stored bytes:", f"{optimized_total:,}")
print("Gross payload savings:", f"{gross_savings:,}")
print("Gross payload increases:", f"{gross_increases:,}")
print("Net payload savings:", f"{original_total - optimized_total:,}")

print("\nImproved records:", improved)
print("Unchanged records:", unchanged)
print("Increased records:", increased)

print("\n=== TOP 15 SAVINGS ===")

for saving, name, old, new in sorted(
    results, reverse=True
)[:15]:
    print(f"\n{name}")
    print("Original:", f"{old:,}")
    print("Optimized:", f"{new:,}")
    print("Savings:", f"{saving:,}")

print("\nIMPORTANT:")
print("These are estimated payload savings only.")
print("They do not include archive alignment or metadata.")
print("No files were modified.")
