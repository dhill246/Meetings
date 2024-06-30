import subprocess


# Function to convert a file into a .wav file
# TODO -- Move this into a helper folder
def convert_to_wav(input_file, output_file):

    ffmpeg_path = r'C:\Program Files\ffmpeg\bin\ffmpeg.exe'  # Adjust the path according to your actual ffmpeg installation

    # Fmmpeg command to convert the input file to WAV format
    command = [ffmpeg_path, '-i', input_file, output_file]

    try:
        # Execute the command and capture output
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Check if the command was successful
        if result.returncode != 0:
            # Output error if ffmpeg failed
            print("ffmpeg error:", result.stderr)
        else:
            print("Conversion successful:", result.stdout)

    except FileNotFoundError:
        print("ffmpeg not found. Ensure it is installed and added to your PATH.")
    except Exception as e:
        print("An error occurred:", str(e))

if __name__ == "__main__":
    convert_to_wav("1.webm", "1.wav")
    convert_to_wav("2.webm", "2.wav")
    convert_to_wav("3.webm", "3.wav")