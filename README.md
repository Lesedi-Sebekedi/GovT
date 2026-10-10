# GovVacancy SA

A static-first prototype for finding South African public service vacancies. It is built with plain HTML, CSS and JavaScript, so GitHub Pages can host it without a server, database, build step or paid service.

## Run locally

Open `index.html` in a browser. The prototype uses bundled example listings in `vacancies.js`; no local server or package installation is required.

## Publish with GitHub Pages

1. Push this project to a GitHub repository, using `main` as the default branch.
2. In the repository, open **Settings → Pages** and set the build and deployment source to **GitHub Actions**.
3. Push to `main` (or run the **Deploy static site to GitHub Pages** workflow from the Actions tab).
4. Open the Pages URL shown in the repository settings.

The workflow publishes the repository's static site files. Search, filters, vacancy details and saved listings work entirely in the visitor's browser. Saved listings use local browser storage and are not synced between devices.

## Automatic DPSA circular updates

The **Update vacancies and deploy** GitHub Actions workflow checks the DPSA vacancy page every Friday at 07:00 and 14:00 South African time, and can also be run manually from the Actions tab. It follows recent circular pages, downloads each department/province advertisement PDF, extracts text with PyMuPDF, keeps current unexpired listings, and deploys the updated static site. Successful data updates are committed back to the repository.

The extractor recognizes common DPSA advert fields such as post title, reference, salary, centre, requirements, duties and closing date. Circular PDFs do not all use identical layouts. Listings are marked as automatically extracted, and the official PDF is linked as the authoritative source. Scanned/image-only PDFs or unfamiliar layouts may need manual review; extraction failures are shown in the Actions log and the workflow retries the circular on a later run.

## Set up GitHub Pages

1. Push this project to a GitHub repository, using `main` as the default branch.
2. In **Settings → Pages**, set the build and deployment source to **GitHub Actions**.
3. In **Settings → Actions → General → Workflow permissions**, allow read and write permissions so the updater can commit refreshed listing data.
4. Push to `main`, then run **Update vacancies and deploy** once from the Actions tab to populate the first live dataset. It will continue checking each Friday automatically.

GitHub Actions runs the scheduled scraper and publishes the static site; no always-on server or database is needed. GitHub may delay scheduled jobs during periods of high load. User accounts, cross-device saved jobs, private notifications and server-side AI would need a separate backend or hosted service.

## Run the extractor locally

Install Python 3.11+ and `requirements.txt`, then run `python scripts/update_vacancies.py`. Run the parser tests with `python -m unittest discover -s tests -v`.

## Important

Only vacancies with a future closing date are kept. The source circular and individual PDF links are preserved in each listing. The DPSA issues the circular but directs vacancy enquiries to the advertising department; applicants must follow the original advert.
