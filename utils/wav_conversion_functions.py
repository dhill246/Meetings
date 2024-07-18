import os
import subprocess

def convert_to_wav(input_file, output_file):
    ffmpeg_path = r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"  # Adjust the path according to your actual ffmpeg installation

    # Ffmpeg command to convert the input file to WAV format
    command = [ffmpeg_path, "-i", input_file, output_file]
    print("Executing command:", " ".join(command))

    try:
        # Execute the command with a timeout
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        # Check if the command was successful
        if result.returncode != 0:
            # Output error if ffmpeg failed
            print("ffmpeg error:", result.stderr)
        else:
            print("Conversion successful:", result.stdout)

    except subprocess.TimeoutExpired:
        print("The ffmpeg process took too long and was terminated.")
    except FileNotFoundError:
        print("ffmpeg not found. Ensure it is installed and added to your PATH.")
    except Exception as e:
        print("An error occurred:", str(e))

def convert_files_to_wav(base_dir, target_dir):
    """
    Iterates through all the files in the base directory and converts them to .wav files in the target directory.

    Args:
        base_dir (str): The base directory containing the original files.
        target_dir (str): The target directory to store the converted .wav files.
    """
    for user in os.listdir(base_dir):
        userpath = os.path.join(base_dir, user)
        for report in os.listdir(userpath):
            reportpath = os.path.join(userpath, report)
            for date in os.listdir(reportpath):
                print(date)
                datepath = os.path.join(reportpath, date)
                wav_path = os.path.join(target_dir, user, report, date)
                
                os.makedirs(wav_path, exist_ok=True)
                
                for file in os.listdir(datepath):                
                    print(file)
                    filepath = os.path.join(datepath, file)
                    pre = os.path.splitext(file)[0]
                    full_wav_path = os.path.join(wav_path, pre + ".wav")
                    print(f"Converting {filepath} to {full_wav_path}")
                    convert_to_wav(filepath, full_wav_path)