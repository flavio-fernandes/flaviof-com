# flaviof-com

flaviof Blog Site (v2)

This repo holds the contents for what is published under:

http://flaviof.com/blog2

Howto
=====

To generate this site, follow the instructions below:

1. Clone this repository

   `git clone git@github.com:flavio-fernandes/flaviof-com.git && cd flaviof-com`

2. To render drafts on local server, run the command shown below:

   $ hugo server --buildDrafts --watch

3. Build the site using hugo

   `hugo`

4. Sync the content out to your hosting provider:

   `rsync -avz --delete -e ssh public/* flaviof.com:flaviof.com/blog2/`

5. You're done!

To create a new post, run a command such as the following:

   `hugo new post/hacks/test.md'

References
==========
This Readme file was copied from and inspired by the following links:

* Original flaviof.com blog: https://github.com/flavio-fernandes/pelican-blog
* Silicon Loons Blog Site: https://github.com/mestery/siliconloons
* David Allen Website: http://davidrallen.com/

The following are links for references for working with Hugo and Markdown:

* Hugo commands: http://gohugo.io/commands/
* Toml notation:  https://github.com/toml-lang/toml
* Markdown Cheatsheet: https://github.com/adam-p/markdown-here/wiki/Markdown-Cheatsheet

