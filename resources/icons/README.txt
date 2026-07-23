civiltools logo assets

Source files:
- civiltools.svg: square app icon source.
- civiltools-logo.svg: horizontal wordmark source.

Generated app icon files:
- civiltools.ico
- civiltools-16.png
- civiltools-32.png
- civiltools-48.png
- civiltools-64.png
- civiltools-128.png
- civiltools-256.png

Regenerate the Windows icon with ImageMagick:
magick convert civiltools.svg -define icon:auto-resize=256,128,64,48,32,16 civiltools.ico
