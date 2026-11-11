"""untalk.py [max]: press Circle until no talk box is open (box frame rows are neutral grey: y 80 for a
top box, y 160 for a bottom one; probed at x 160). Prints the number of presses."""
import os, subprocess, sys, tempfile
from PIL import Image
D = os.path.dirname(os.path.abspath(__file__))


def boxed(path):
    im = Image.open(path).convert('RGB')
    k = im.width // 320                      # screenshots are internal resolution (4x with the hardware renderer)
    for y in (79, 80, 81, 159, 160, 161):
        r, g, b = im.getpixel((160 * k + k // 2, y * k + k // 2))
        if max(r, g, b) - min(r, g, b) <= 2 and 60 < r < 200:
            return True
    return False


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    shot = os.path.join(tempfile.gettempdir(), 'untalk.png')
    for k in range(n):
        subprocess.run([os.path.join(D, 'hshot.sh'), shot], check=True)
        if not boxed(shot):
            print(k)
            return
        subprocess.run([os.path.join(D, 'hpress.sh'), '/dev/null', 'X', 'w'], check=True)
    print('still open after', n)


if __name__ == '__main__':
    main()
