import os
import sys

# Force standard stdout encoding to utf-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def read_log():
    log_path = "bot_err.log"
    if not os.path.exists(log_path):
        print("Log file does not exist")
        return
        
    with open(log_path, "rb") as f:
        content = f.read()
        
    # Try decoding as UTF-16-LE first
    try:
        decoded = content.decode("utf-16")
        print("Decoded as UTF-16 successfully")
    except Exception:
        try:
            decoded = content.decode("utf-8", errors="ignore")
            print("Decoded as UTF-8")
        except Exception as e:
            print("Failed to decode:", e)
            return
            
    lines = decoded.splitlines()
    print(f"Total lines: {len(lines)}")
    
    # Print the last 100 lines, replacing any unencodable characters
    for line in lines[-100:]:
        print(line.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))

if __name__ == "__main__":
    read_log()
