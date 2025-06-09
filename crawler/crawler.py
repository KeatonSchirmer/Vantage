import bs4
import requests
import datetime

#TODO - Function to bypass LinkedIn login page and scrape jobs
#TODO - Function to scrape job details from the job page
#TODO - Function to go to company website from the linkedIn page
#TODO - Function to store data in database
#TODO - Function to search company website from Ezilon directory
#TODO - Function to take user input to pull data from database
#TODO - Create a timer to run the script every several hours



class LinkedInScraper:
    #* Working Job Scraper for linkedIn

    url_l = "https://www.linkedin.com/jobs/search/?keywords=college+internship"

    soup_l = bs4.BeautifulSoup(requests.get(url_l).text, "html.parser")

    def l_listings(soup_l):
        infos = []
        listings_container = soup_l.find("ul", class_="jobs-search__results-list")
        if listings_container:
            listings = listings_container.find_all("li")
            for info in listings:
                job = info.find('h3')
                company = info.find('h4')
                location = info.find('span', class_='job-search-card__location')
                url = info.find('a', class_='base-card__full-link')['href']
                posted = info.find('time')['datetime']
                if posted:
                    posted_date = datetime.datetime.strptime(posted, "%Y-%m-%d")
                    now = datetime.datetime.now()
                    recent_post = now - datetime.timedelta(days=14)
                    if posted_date >= recent_post:
                        infos.append({
                            'job': job.text.strip() if job else None,
                            'company': company.text.strip() if company else None,
                            'location': location.text.strip() if location else None,
                            'url': url if url else None,
                            'posted': posted if posted else None
                        })
        return infos
    

class EzilonScraper:
    #* Working Ezilon Scraper for manually input

    url_e = "https://search.ezilon.com/united_states/business/engineering/environmental_engineering/index.shtml"

    soup_e = bs4.BeautifulSoup(requests.get(url_e).text, "html.parser")

    def e_listings(soup_e):
        infos = []
        listings_container = soup_e.find('ul', class_='listing')
        if listings_container:
            listings = listings_container.find_all('li')
            for info in listings:
                company = info.find('a', class_='title')
                url = info.find('span', class_='url')
                infos.append({
                    'company': company.text.strip() if company else None,
                    'url': url.text.strip() if url else None
                })

        return infos

    #print(e_listings(soup_e))

    #* Base scraper for Ezilon

    def primary_scrape(seed_url):
        try:
            response = requests.get(seed_url)
            response.raise_for_status()
            soup = bs4.BeautifulSoup(response.text, 'html.parser')

            links = []
            url_container = soup.find('ul', class_='category_list')     #? Takes urls from only the directory table
            if url_container:
                urls = url_container.find_all('a')
                for url in urls:
                    href = url['href']
                    if not href.startswith('http'):
                        href = requests.compat.urljoin(seed_url, href)      #? Makes URL absolute and usable
                    links.append(href)
                print(f'Found {url.text.strip()} on Ezilon Business page.')
                return links
        except requests.exceptions.RequestException as e:
            print(f"1.1 Error fetching {seed_url}: {e}")
            return []
        
    #* Scraper for Ezilon results

    def secondary_scrape(url):
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = bs4.BeautifulSoup(response.text, 'html.parser')

            try:
                sub_links = []
                url_container = soup.find('ul', class_='category_list')     #? Takes urls from only the directory table
                if url_container:
                    urls = url_container.find_all('a')
                    for url in urls:
                        href = url['href']
                        if not href.startswith('http'):
                            href = requests.compat.urljoin(url, href)      #? Makes URL absolute and usable
                        sub_links.append(href)
                        print(f'Found {url.text.strip()} companies')
                else:
                    print(f'No sub-links found on {url}')
                return sub_links
            except requests.exceptions.RequestException as e:
                print(f"2.1 Error fetching {url}: {e}")
                return []

        except requests.exceptions.RequestException as e:
            print(f"2.2 Error fetching {url}: {e}")
            return []

    #* Scraper to get company names and urls from each sub-link

    def final_scrape(url): 
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = bs4.BeautifulSoup(response.text, 'html.parser')
            infos = []
            urls = []
            listings_container = soup.find('ul', class_='listing')
            if listings_container:
                listings = listings_container.find_all('li')
                for info in listings:
                    company = info.find('a', class_='title')
                    url = info.find('span', class_='url')               #? Puts url in a variable to be used later
                    if url:
                        urls.append(url.text.strip())
                    print(f'Company: {company.text.strip()}, URL: {url.text.strip()}')      #? Prints the company name and URL to the console
                    infos.append({
                        'company': company.text.strip() if company else None,
                        'url': url.text.strip() if url else None
            })
            return infos, urls

        except requests.exceptions.RequestException as e:
            print(f"3.1 Error fetching {url}: {e}")
            return [], []
        

    def company_search(url, keyword):
        try:
            response = requests.get (url)
            response.raise_for_status()
            soup = bs4.BeautifulSoup(response.text, 'html.parser')

            try:
                career = soup.find_all(['div','class','a'], string=lambda text: text and keyword.lower() in text.lower())
                for result in career:
                    print(f'Found: {result.strip()} in tag <{result.parent.name}>')
                return career
                    
            except requests.exceptions.RequestException as e:
                print(f"4.1 Error fetching {url}: {e}")
                return []
                

        except requests.exceptions.RequestException as e:
            print(f"4.2 Error fetching {url}: {e}")
            return []


    def process_urls(urls):
        for url in urls:
            print(f'Processing URL: {url}')
            
    #? This keeps the script from running unprompted
    if __name__ == '__main__':
        seed_url = "https://search.ezilon.com/united_states/business/index.shtml"
        first = primary_scrape(seed_url)
        keyword = 'career'
        for link in first:
            second = secondary_scrape(link)
            if not second:
                print(f'No sub-links found for {link}')
                continue
            for sub_link in second:
                final_results, urls = final_scrape(sub_link)
                process_urls(urls)

class GoogleScraper:            
    #* Google Custom Search Scaper

    #! IMPORTANT TASKS
    #TODO - Save the results to a database


    #* Not as Urgent Tasks
    #TODO - Function to use input from user as query (Take user input from app or website)
    #TODO - Narrow down the search to specific categories (Company, URL, Snippet of Job Description, Location, etc.)

    @staticmethod
    def search_api(user_query, total_results, params, url, ignore_keywords, results_per_page):
        queries = [
            f'{user_query} internships',
            f'{user_query} companies',
            f'{user_query} internship requirements',
            f'{user_query} ideal internship and career path'
        ]
        all_results = []
        for query in queries:
            current_start = 1
            results_fetched = 0
            while results_fetched < total_results:
                local_params = params.copy()
                local_params['q'] = query
                local_params['start'] = current_start
                response = requests.get(url, params=local_params)
                results = response.json()

                if 'items' not in results:
                    break

                for item in results['items']:
                    title = item.get('title', '').lower()
                    link = item.get('link', '').lower()
                    snippet = item.get('snippet', '').lower()

                    if any(keyword in title for keyword in ignore_keywords) or \
                    any(keyword in link for keyword in ignore_keywords) or \
                    any(keyword in snippet for keyword in ignore_keywords):
                        continue

                    # Optional: Remove or comment out the HEAD request for speed
                    # try:
                    #     head_resp = requests.head(link, timeout=3, allow_redirects=True)
                    #     if head_resp.status_code != 200:
                    #         continue
                    # except Exception:
                    #     continue

                    all_results.append({
                        'title': item.get('title', 'No title'),
                        'link': item.get('link', 'No link'),
                        'snippet': item.get('snippet', 'No snippet'),
                        'category': query.replace(user_query, '').strip()
                    })
                    results_fetched += 1
                    if results_fetched >= total_results:
                        break

                if len(results['items']) < results_per_page:
                    # No more results on next pages
                    break

                current_start += results_per_page

        return all_results

    if __name__ == '__main__':
        user_query = input('Degree: ')
        url = 'https://customsearch.googleapis.com/customsearch/v1'
        ignore_keywords = ['linkedin', 'indeed', 'wikipedia']
        total_results = 40
        results_per_page = 10
        params = {
            'key': 'AIzaSyDq_GFJzlkOQV0R0EFBD8iVdyCvqypLbk4',
            'cx': 'f43b15d72db4d49d3',
            # 'q' will be overridden inside search_api
        }

        results = search_api(user_query, total_results, params, url, ignore_keywords, results_per_page)
        print(f"Total results: {len(results)}")
        for r in results:
            print(r['title'], r['link'])

class TemporaryScraper:
    def temporary_search(query, max_results=10):
        search_url = 'https://www.linkedin.com/jobs/search/?currentJobId=4238101062&keywords=college%20internship'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
        resp = requests.get(search_url, headers=headers)
        soup = bs4.BeautifulSoup(resp.text, "html.parser")
        results = []
        for card in soup.select('ul.jobs-search__results-list li')[:max_results]:
            title = card.find('h3').get_text(strip=True) if card.find('h3') else 'No title'
            company = card.find('h4').get_text(strip=True) if card.find('h4') else 'No company'
            location = card.find('span', class_='job-search-card__location').get_text(strip=True) if card.find('span', class_='job-search-card__location') else 'No location'
            url = card.find('a', class_='base-card__full-link')['href'] if card.find('a', class_='base-card__full-link') else '#'
            job_desc = card.find('p', class_='job-search-card__snippet').get_text(strip=True) if card.find('p', class_='job-search-card__snippet') else 'No description'
            requirements = card.find('ul', class_='job-search-card__requirements').get_text(strip=True) if card.find('ul', class_='job-search-card__requirements') else 'No requirements'
            ideal = card.find('ul', class_='job-search-card__ideal').get_text(strip=True) if card.find('ul', class_='job-search-card__ideal') else 'No ideal candidate description'
            if url and url != '#':
                detail_resp = requests.get(url, headers=headers)
                detail_soup = bs4.BeautifulSoup(detail_resp.text, "html.parser")
                # You need to inspect LinkedIn's job detail page HTML to find the correct selectors
                desc_elem = detail_soup.find('div', class_='description__text')
                job_desc = desc_elem.get_text(strip=True) if desc_elem else ''
                # requirements and ideal would need similar logic if available    
            results.append({
                'title': title,
                'company': company,
                'location': location,
                'link': url,
                'description': job_desc,
                'requirements': requirements,
                'ideal': ideal
            })
        return results

#f"https://www.linkedin.com/jobs/search/?keywords={query}&f_E=2"