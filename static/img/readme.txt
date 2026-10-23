The images in this tree are tracked in git, alongside the posts that use
them. A fresh clone has everything needed to build the site:

    git pull && hugo

This was not always so. These files used to live outside the repo, synced
between machines by Dropbox, with static/img listed in .gitignore. A machine
holding an incomplete copy would build a public/ missing images, and the
publish step

    rsync -avz --delete -e ssh public/* flaviof.com:flaviof.com/blog2/

would then delete those images from the live server. That happened, which is
why they are committed now.

Two things worth knowing when adding images here:

  - Reference them from a post as img/<dir>/<file>. The built pages carry
    <base href="https://www.flaviof.com/blog2/">, so that resolves to
    /blog2/img/<dir>/<file>.

  - macOS leaves resource-fork droppings (._* files and .DS_Store) in this
    tree. They are gitignored, and config.toml excludes them at the static
    mount, so they reach neither public/ nor the live server.
