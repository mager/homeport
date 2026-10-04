# Homeport public site

Static landing page, deployed at https://homeport-gamma.vercel.app/ in the dedicated Vercel project `homeport`. No runtime secrets, private control endpoints, build dependencies, or analytics. The actual workspace still runs privately on the Mini.

Preview from the repository root:

```sh
python3 -m http.server 4391 --directory site
```

Publish from this directory, using an account with access to the project:

```sh
vercel link --project homeport
vercel deploy --prod
```

The connection walkthrough is a labeled simulation. The workspace image is an actual product screenshot. Fonts are self-hosted Geist and Geist Mono under the included SIL Open Font License. Keep the canonical URL, social metadata, robots, and sitemap in sync if the domain changes.
