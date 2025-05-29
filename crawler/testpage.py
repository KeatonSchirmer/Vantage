

#? REBUILDING CRAWLERS
#* Search screen will take a set amount of results while crawler still searches for more in the background to reduce 
#* the time it takes to get results.
#* Search screen will cache the results for about 2 hours, to optimize the search time.
#* SOHOME will show some random results and wont have a view link button the whole card will be a link to the job posting.

#! LinkedIn Crawler
    #* Searches for internship which includes (
        #* - Company
        #* - Job Position
        #* - Location
        #* - Date Posted
        #* - Job Description [Job Responsibilities, Job Requirements, Job Preferences]
        #* - Posting URL
        #* - Company URL)
    #* Crawler needs to click on to posting to get the full description
        #! Requires a login to get the full description 

#! Google API Crawler
    #* Searches for internship which includes (
    #* - Company
    #* - Job Position
    #* - Location
    #* - Date Posted
    #* - Job Description [Job Responsibilities, Job Requirements, Job Preferences]
    #* - Posting URL
    #* - Company URL)

import bs4
import requests
import datetime


url_l = "https://www.linkedin.com/jobs/search/?keywords=college+internship"

soup_l = bs4.BeautifulSoup(requests.get(url_l).text, "html.parser")
url = 'https://customsearch.googleapis.com/customsearch/v1'

def base_search(soup_l):
    infos = []
    listings_container = soup_l.find("ul", class_="jobs-search__results-list")
    all_results = []
    print('Listings container:', listings_container)
    if listings_container:
        listings = listings_container.find_all("li")[:10]
        print('Listings found:', len(listings))
        for info in listings:
            job = info.find('h3')
            company = info.find('h4')
            search_terms = ""
            if job:
                search_terms += job.text.strip() if job else None
            if company:
                search_terms += " " + company.text.strip() if company else None
            if not search_terms:
                continue

            query = str(search_terms)
            current_start = 1
            results_fetched = 0
            while results_fetched < 10:
                params = {
                    'key': 'AIzaSyDRev_yjHadZmkCkxqYP8Y4XzxEahLp1gA',  #! API Quota maxed outn as of 5-28-2025
                    'cx': '23c933d7a0f4840b0',
                    'q': query,
                    'start': current_start
                }
                response = requests.get(url, params=params)
                data = response.json()
                print('Response data:', data)
                if 'items' in data:
                    for item in data['items']:
                        job = item.get('title', 'No title available')
                        link = item.get('link', 'No link available')
                        snippet = item.get('snippet', 'No snippet available')
                    #        head_resp = requests.head(link, timeout=3, allow_redirects=True)
                    #        if head_resp.status_code == 200:
                        all_results.append({
                            'job': job,
                            'link': link,
                            'snippet': snippet,
                        })
                        results_fetched += 1
                        if results_fetched >= 10:
                            break
                    #    except requests.RequestException as e:
                    #        print(f"Error fetching {link}: {e}")
                    current_start += 10
                else:
                    break
        return all_results

print(base_search(soup_l))
            
