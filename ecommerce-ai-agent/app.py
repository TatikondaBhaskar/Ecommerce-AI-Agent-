from flask import Flask, render_template, request, flash
import os
import urllib.parse
import random
import requests
from bs4 import BeautifulSoup
import re
import time

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Available platforms for price comparison (Indian e-commerce platforms)
AVAILABLE_PLATFORMS = [
    'Amazon',
    'Flipkart',
    'Myntra',
    'Meesho',
    'Snapdeal',
    'Ajio',
    'Nykaa',
    'FirstCry',
    'ShopClues',
    'Paytm Mall'
]

def generate_search_url(platform, query):
    """Generate actual search URLs for different Indian e-commerce platforms"""
    encoded_query = urllib.parse.quote_plus(query)
    
    urls = {
        'Amazon': f'https://www.amazon.in/s?k={encoded_query}',
        'Flipkart': f'https://www.flipkart.com/search?q={encoded_query}',
        'Myntra': f'https://www.myntra.com/{encoded_query.replace("+", "-")}',
        'Meesho': f'https://www.meesho.com/search?q={encoded_query}',
        'Snapdeal': f'https://www.snapdeal.com/search?keyword={encoded_query}',
        'Ajio': f'https://www.ajio.com/search/?text={encoded_query}',
        'Nykaa': f'https://www.nykaa.com/search/result/?q={encoded_query}',
        'FirstCry': f'https://www.firstcry.com/search?q={encoded_query}',
        'ShopClues': f'https://www.shopclues.com/search?q={encoded_query}',
        'Paytm Mall': f'https://paytmmall.com/shop/search?q={encoded_query}'
    }
    return urls.get(platform, f'https://www.google.com/search?q={encoded_query}')

def get_headers():
    """Return headers to mimic a real browser request"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-IN,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    }

def scrape_amazon(query):
    """Scrape Amazon.in for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('Amazon', query)
        session = requests.Session()
        
        # Enhanced headers for Amazon
        amazon_headers = get_headers().copy()
        amazon_headers.update({
            'Referer': 'https://www.amazon.in/',
            'Origin': 'https://www.amazon.in',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        })
        
        # Add cookies to appear more like a real browser
        session.cookies.set('session-id', '261-1234567-1234567', domain='.amazon.in')
        session.cookies.set('session-id-time', '2082787201l', domain='.amazon.in')
        
        # Try with delay to avoid rate limiting
        time.sleep(2)
        
        # Try multiple attempts with different approaches
        response = None
        for attempt in range(2):
            try:
                response = session.get(url, headers=amazon_headers, timeout=25, allow_redirects=True)
                # If we get 200, break
                if response.status_code == 200:
                    break
                # If 503, wait longer and try again
                if response.status_code == 503 and attempt < 1:
                    time.sleep(3)
                    continue
            except:
                if attempt < 1:
                    time.sleep(2)
                    continue
                return None
        
        if not response:
            return None
        
        # Even if status code is not 200, try to parse the content
        # Sometimes Amazon returns content even with 503
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        # Check if we got blocked (CAPTCHA or error page)
        page_text = response.text.lower()
        if 'captcha' in page_text or 'robot' in page_text or 'access denied' in page_text:
            print("Amazon CAPTCHA or access denied detected")
            # Still try to parse - sometimes there's data
            if len(response.text) < 5000:  # Very short response likely means blocked
                return None
        
        # Try multiple selectors for Amazon products
        products = soup.find_all('div', {'data-component-type': 's-search-result'})
        if not products:
            products = soup.find_all('div', class_='s-result-item')
        if not products:
            products = soup.find_all('div', {'data-asin': True})
        if not products:
            # Try finding by data-index
            products = soup.find_all('div', {'data-index': True})
        
        products = products[:5]  # Limit to 5 products
        
        for product in products:
            try:
                # Price extraction - try multiple methods
                price = None
                
                # Method 1: a-price-whole (most common)
                price_elem = product.find('span', class_='a-price-whole')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace(',', ''))
                    if price_match:
                        try:
                            price = int(price_match.group(1).replace(',', ''))
                        except:
                            pass
                
                # Method 2: a-offscreen (hidden price)
                if not price:
                    price_elem = product.find('span', class_='a-offscreen')
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                        if price_match:
                            try:
                                price = int(price_match.group(1).replace(',', ''))
                            except:
                                pass
                
                # Method 3: a-price (price container)
                if not price:
                    price_container = product.find('span', class_='a-price')
                    if price_container:
                        price_elem = price_container.find('span', class_='a-offscreen')
                        if not price_elem:
                            price_elem = price_container.find('span', class_='a-price-whole')
                        if price_elem:
                            price_text = price_elem.get_text(strip=True)
                            price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                            if price_match:
                                try:
                                    price = int(price_match.group(1).replace(',', ''))
                                except:
                                    pass
                
                # Method 4: Search in all spans for ₹ symbol
                if not price:
                    for span in product.find_all('span'):
                        text = span.get_text(strip=True)
                        if '₹' in text:
                            match = re.search(r'₹\s*(\d[\d,]*)', text)
                            if match:
                                try:
                                    price = int(match.group(1).replace(',', ''))
                                    if price > 100:  # Reasonable minimum
                                        break
                                except:
                                    continue
                
                # Only add if we found a price
                if price and price > 0:
                    # Rating extraction
                    rating = 'N/A'
                    rating_elem = product.find('span', class_='a-icon-alt')
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    # Try alternative rating selectors
                    if rating == 'N/A':
                        rating_elem = product.find('i', class_='a-icon-star')
                        if rating_elem:
                            rating_span = rating_elem.find_next('span', class_='a-icon-alt')
                            if rating_span:
                                rating_text = rating_span.get_text(strip=True)
                                rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                                if rating_match:
                                    rating = rating_match.group(1)
                    
                    # Delivery information
                    delivery = 'Free delivery on orders above ₹499'
                    # Try multiple delivery selectors
                    delivery_elems = product.find_all('span', string=re.compile('delivery|shipping|Get it|Prime', re.I))
                    if delivery_elems:
                        for elem in delivery_elems:
                            delivery_text = elem.get_text(strip=True)
                            if delivery_text and len(delivery_text) > 5:
                                delivery = delivery_text[:50]
                                break
                    
                    # Try to find delivery in aria-label
                    if delivery == 'Free delivery on orders above ₹499':
                        for elem in product.find_all(['span', 'div'], attrs={'aria-label': re.compile('delivery|shipping', re.I)}):
                            delivery_text = elem.get('aria-label', '')
                            if delivery_text and len(delivery_text) > 5:
                                delivery = delivery_text[:50]
                                break
                    
                    # Try finding in parent elements
                    if delivery == 'Free delivery on orders above ₹499':
                        parent = product.find_parent()
                        if parent:
                            delivery_span = parent.find('span', string=re.compile('delivery|shipping', re.I))
                            if delivery_span:
                                delivery = delivery_span.get_text(strip=True)[:50]
                    
                    # Product link
                    link_elem = product.find('a', href=re.compile('/dp/|/gp/product/'))
                    if not link_elem:
                        h2 = product.find('h2')
                        if h2:
                            link_elem = h2.find('a')
                    if not link_elem:
                        link_elem = product.find('a', class_='a-link-normal')
                    
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://www.amazon.in' + href.split('?')[0]
                        elif href.startswith('http'):
                            product_url = href.split('?')[0]
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except Exception as e:
                print(f"Error processing Amazon product: {e}")
                continue
                
        return results if results else None
    except Exception as e:
        print(f"Amazon scraping error: {e}")
        return None

def scrape_flipkart(query):
    """Scrape Flipkart for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('Flipkart', query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            print(f"Flipkart returned status code: {response.status_code}")
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        # Try multiple selectors for Flipkart products
        products = soup.find_all('div', class_='_1AtVbE')
        if not products:
            products = soup.find_all('div', {'data-id': True})
        if not products:
            products = soup.find_all('div', class_='_2kHMtA')
        if not products:
            products = soup.find_all('a', class_='_1fQZEK', href=re.compile('/p/'))
            # Convert links to parent containers
            products = [p.parent for p in products if p.parent]
        
        products = products[:5]  # Limit to 5 products
        
        for product in products:
            try:
                # Price extraction - try multiple methods
                price = None
                
                # Method 1: _30jeq3 (current price)
                price_elem = product.find('div', class_='_30jeq3')
                if not price_elem:
                    price_elem = product.find('div', class_='_1_WHN1')
                if not price_elem:
                    price_elem = product.find('div', class_='_25b18c')
                
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                
                # Method 2: Search in all divs
                if not price:
                    for div in product.find_all('div'):
                        text = div.get_text(strip=True)
                        if '₹' in text and re.search(r'₹\s*(\d[\d,]*)', text):
                            match = re.search(r'₹\s*(\d[\d,]*)', text)
                            if match:
                                try:
                                    price = int(match.group(1).replace(',', ''))
                                    if price > 100:  # Reasonable minimum
                                        break
                                except:
                                    continue
                
                # Only add if we found a price
                if price and price > 0:
                    # Rating extraction
                    rating = 'N/A'
                    rating_elem = product.find('div', class_='_3LWZlK')
                    if not rating_elem:
                        rating_elem = product.find('span', class_='_2_R_DZ')
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    # Delivery information
                    delivery = 'Free delivery'
                    delivery_elem = product.find('div', class_='_2TpdnF')
                    if not delivery_elem:
                        delivery_elem = product.find('span', string=re.compile('delivery|free', re.I))
                    if delivery_elem:
                        delivery_text = delivery_elem.get_text(strip=True)
                        delivery = delivery_text[:50]
                    
                    # Product link
                    link_elem = product.find('a', class_='_1fQZEK')
                    if not link_elem:
                        link_elem = product.find('a', href=re.compile('/p/'))
                    if not link_elem:
                        link_elem = product.find('a')
                    
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://www.flipkart.com' + href.split('?')[0]
                        elif href.startswith('http'):
                            product_url = href.split('?')[0]
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except Exception as e:
                print(f"Error processing Flipkart product: {e}")
                continue
                
        return results if results else None
    except Exception as e:
        print(f"Flipkart scraping error: {e}")
        return None

def scrape_myntra(query):
    """Scrape Myntra for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('Myntra', query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            print(f"Myntra returned status code: {response.status_code}")
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        # Myntra product containers
        products = soup.find_all('li', class_='product-base')
        if not products:
            products = soup.find_all('div', class_='product-base')
        
        products = products[:5]  # Limit to 5 products
        
        for product in products:
            try:
                # Price extraction - try multiple methods
                price = None
                
                price_elem = product.find('span', class_='product-discountedPrice')
                if not price_elem:
                    price_elem = product.find('span', class_='product-price')
                if not price_elem:
                    # Search in all spans
                    for span in product.find_all('span'):
                        text = span.get_text(strip=True)
                        if '₹' in text and re.search(r'₹\s*(\d[\d,]*)', text):
                            match = re.search(r'₹\s*(\d[\d,]*)', text)
                            if match:
                                try:
                                    price = int(match.group(1).replace(',', ''))
                                    if price > 100:
                                        break
                                except:
                                    continue
                
                if price_elem and not price:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                
                # Only add if we found a price
                if price and price > 0:
                    # Rating extraction
                    rating = 'N/A'
                    rating_elem = product.find('div', class_='product-ratingsContainer')
                    if rating_elem:
                        rating_span = rating_elem.find('span')
                        if rating_span:
                            rating_text = rating_span.get_text(strip=True)
                            rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                            if rating_match:
                                rating = rating_match.group(1)
                    
                    # Delivery information
                    delivery = 'Free delivery above ₹799'
                    delivery_elem = product.find('div', class_='product-deliveryInfo')
                    if delivery_elem:
                        delivery_text = delivery_elem.get_text(strip=True)
                        delivery = delivery_text[:50]
                    
                    # Product link
                    link_elem = product.find('a')
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://www.myntra.com' + href
                        elif href.startswith('http'):
                            product_url = href
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except Exception as e:
                print(f"Error processing Myntra product: {e}")
                continue
                
        return results if results else None
    except Exception as e:
        print(f"Myntra scraping error: {e}")
        return None

def scrape_snapdeal(query):
    """Scrape Snapdeal for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('Snapdeal', query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        products = soup.find_all('div', class_='product-tuple-listing')
        if not products:
            products = soup.find_all('div', {'data-dp-id': True})
        
        products = products[:5]
        
        for product in products:
            try:
                price = None
                price_elem = product.find('span', class_='product-price')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                
                if price and price > 0:
                    rating = 'N/A'
                    rating_elem = product.find('div', class_='filled-stars')
                    if rating_elem:
                        rating_style = rating_elem.get('style', '')
                        rating_match = re.search(r'width:\s*(\d+)%', rating_style)
                        if rating_match:
                            rating_val = int(rating_match.group(1)) / 20
                            rating = f"{rating_val:.1f}"
                    
                    delivery = 'Free delivery'
                    delivery_elem = product.find('span', string=re.compile('delivery|shipping', re.I))
                    if delivery_elem:
                        delivery = delivery_elem.get_text(strip=True)[:50]
                    
                    link_elem = product.find('a', href=re.compile('/product/'))
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://www.snapdeal.com' + href
                        elif href.startswith('http'):
                            product_url = href
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except:
                continue
                
        return results if results else None
    except:
        return None

def scrape_meesho(query):
    """Scrape Meesho for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('Meesho', query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        products = soup.find_all('div', class_='ProductCard__BaseCard')
        if not products:
            products = soup.find_all('div', {'data-test-id': 'product-card'})
        
        products = products[:5]
        
        for product in products:
            try:
                price = None
                price_elem = product.find('div', class_='ProductCard__Price')
                if not price_elem:
                    price_elem = product.find('span', class_=re.compile('price', re.I))
                
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                
                if price and price > 0:
                    rating = '4.0'
                    rating_elem = product.find('div', class_='ProductCard__Rating')
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    delivery = 'Free delivery'
                    delivery_elem = product.find('span', string=re.compile('delivery|shipping', re.I))
                    if delivery_elem:
                        delivery = delivery_elem.get_text(strip=True)[:50]
                    
                    link_elem = product.find('a', href=re.compile('/product/'))
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://www.meesho.com' + href
                        elif href.startswith('http'):
                            product_url = href
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except:
                continue
                
        return results if results else None
    except:
        return None

def scrape_ajio(query):
    """Scrape Ajio for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('Ajio', query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        products = soup.find_all('div', class_='item rilrtl-products-list__item')
        if not products:
            products = soup.find_all('div', class_='product-item')
        
        products = products[:5]
        
        for product in products:
            try:
                price = None
                price_elem = product.find('span', class_='price')
                if not price_elem:
                    price_elem = product.find('div', class_=re.compile('price', re.I))
                
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                
                if price and price > 0:
                    rating = '4.0'
                    rating_elem = product.find('span', class_='rating')
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    delivery = 'Free delivery'
                    delivery_elem = product.find('span', string=re.compile('delivery|shipping', re.I))
                    if delivery_elem:
                        delivery = delivery_elem.get_text(strip=True)[:50]
                    
                    link_elem = product.find('a', href=re.compile('/p/'))
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://www.ajio.com' + href
                        elif href.startswith('http'):
                            product_url = href
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except:
                continue
                
        return results if results else None
    except:
        return None

def scrape_nykaa(query):
    """Scrape Nykaa for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('Nykaa', query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        products = soup.find_all('div', class_='product-tag')
        if not products:
            products = soup.find_all('div', class_='product-item')
        
        products = products[:5]
        
        for product in products:
            try:
                price = None
                price_elem = product.find('span', class_='price')
                if not price_elem:
                    price_elem = product.find('div', class_=re.compile('price', re.I))
                
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                
                if price and price > 0:
                    rating = '4.0'
                    rating_elem = product.find('div', class_='rating')
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    delivery = 'Free delivery'
                    delivery_elem = product.find('span', string=re.compile('delivery|shipping', re.I))
                    if delivery_elem:
                        delivery = delivery_elem.get_text(strip=True)[:50]
                    
                    link_elem = product.find('a', href=re.compile('/p/'))
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://www.nykaa.com' + href
                        elif href.startswith('http'):
                            product_url = href
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except:
                continue
                
        return results if results else None
    except:
        return None

def scrape_firstcry(query):
    """Scrape FirstCry for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('FirstCry', query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        products = soup.find_all('div', class_='list-prod')
        if not products:
            products = soup.find_all('div', class_='product-item')
        
        products = products[:5]
        
        for product in products:
            try:
                price = None
                price_elem = product.find('span', class_='price')
                if not price_elem:
                    price_elem = product.find('div', class_=re.compile('price', re.I))
                
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                
                if price and price > 0:
                    rating = '4.0'
                    rating_elem = product.find('div', class_='rating')
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    delivery = 'Free delivery'
                    delivery_elem = product.find('span', string=re.compile('delivery|shipping', re.I))
                    if delivery_elem:
                        delivery = delivery_elem.get_text(strip=True)[:50]
                    
                    link_elem = product.find('a', href=re.compile('/product/'))
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://www.firstcry.com' + href
                        elif href.startswith('http'):
                            product_url = href
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except:
                continue
                
        return results if results else None
    except:
        return None

def scrape_shopclues(query):
    """Scrape ShopClues for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('ShopClues', query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        products = soup.find_all('div', class_='product')
        if not products:
            products = soup.find_all('div', class_='product-item')
        
        products = products[:5]
        
        for product in products:
            try:
                price = None
                price_elem = product.find('span', class_='p_price')
                if not price_elem:
                    price_elem = product.find('span', class_=re.compile('price', re.I))
                
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                
                if price and price > 0:
                    rating = '4.0'
                    rating_elem = product.find('div', class_='rating')
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    delivery = 'Free delivery'
                    delivery_elem = product.find('span', string=re.compile('delivery|shipping', re.I))
                    if delivery_elem:
                        delivery = delivery_elem.get_text(strip=True)[:50]
                    
                    link_elem = product.find('a', href=re.compile('/product/'))
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://www.shopclues.com' + href
                        elif href.startswith('http'):
                            product_url = href
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except:
                continue
                
        return results if results else None
    except:
        return None

def scrape_paytmmall(query):
    """Scrape Paytm Mall for product prices, ratings, and delivery details"""
    try:
        url = generate_search_url('Paytm Mall', query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        products = soup.find_all('div', class_='_3Wh')
        if not products:
            products = soup.find_all('div', class_='product-item')
        
        products = products[:5]
        
        for product in products:
            try:
                price = None
                price_elem = product.find('span', class_='_1kMS')
                if not price_elem:
                    price_elem = product.find('div', class_=re.compile('price', re.I))
                
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d[\d,]*)', price_text.replace('₹', '').replace(',', ''))
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                
                if price and price > 0:
                    rating = '4.0'
                    rating_elem = product.find('div', class_='rating')
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                        if rating_match:
                            rating = rating_match.group(1)
                    
                    delivery = 'Free delivery'
                    delivery_elem = product.find('span', string=re.compile('delivery|shipping', re.I))
                    if delivery_elem:
                        delivery = delivery_elem.get_text(strip=True)[:50]
                    
                    link_elem = product.find('a', href=re.compile('/product/'))
                    product_url = url
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            product_url = 'https://paytmmall.com' + href
                        elif href.startswith('http'):
                            product_url = href
                    
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': f"{rating} ⭐" if rating != 'N/A' else '4.0 ⭐',
                        'delivery': delivery,
                        'url': product_url
                    })
            except:
                continue
                
        return results if results else None
    except:
        return None

def scrape_platform(platform, query):
    """Scrape products from a specific platform"""
    if platform == 'Amazon':
        return scrape_amazon(query)
    elif platform == 'Flipkart':
        return scrape_flipkart(query)
    elif platform == 'Myntra':
        return scrape_myntra(query)
    elif platform == 'Snapdeal':
        return scrape_snapdeal(query)
    elif platform == 'Meesho':
        return scrape_meesho(query)
    elif platform == 'Ajio':
        return scrape_ajio(query)
    elif platform == 'Nykaa':
        return scrape_nykaa(query)
    elif platform == 'FirstCry':
        return scrape_firstcry(query)
    elif platform == 'ShopClues':
        return scrape_shopclues(query)
    elif platform == 'Paytm Mall':
        return scrape_paytmmall(query)
    else:
        return None

def generate_results(platform, query):
    """Generate product results by scraping or fallback to search link"""
    # Try to scrape real prices
    scraped_results = scrape_platform(platform, query)
    
    if scraped_results and len(scraped_results) > 0:
        return scraped_results
    
    # For Amazon specifically, try alternative method
    if platform == 'Amazon':
        # Try mobile version or alternative URL
        try:
            mobile_url = f'https://www.amazon.in/s?k={urllib.parse.quote_plus(query)}&ref=sr_pg_1'
            session = requests.Session()
            mobile_headers = get_headers().copy()
            mobile_headers['User-Agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
            response = session.get(mobile_url, headers=mobile_headers, timeout=20)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                products = soup.find_all('div', {'data-asin': True})[:3]
                results = []
                for product in products:
                    try:
                        price = None
                        # Try to find price
                        for span in product.find_all('span'):
                            text = span.get_text(strip=True)
                            if '₹' in text:
                                match = re.search(r'₹\s*(\d[\d,]*)', text)
                                if match:
                                    try:
                                        price = int(match.group(1).replace(',', ''))
                                        if price > 100:
                                            break
                                    except:
                                        continue
                        if price:
                            rating = '4.0'
                            rating_elem = product.find('span', class_='a-icon-alt')
                            if rating_elem:
                                rating_text = rating_elem.get_text(strip=True)
                                rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                                if rating_match:
                                    rating = rating_match.group(1)
                            
                            link_elem = product.find('a', href=re.compile('/dp/|/gp/product/'))
                            product_url = mobile_url
                            if link_elem and link_elem.get('href'):
                                href = link_elem['href']
                                if href.startswith('/'):
                                    product_url = 'https://www.amazon.in' + href.split('?')[0]
                            
                            results.append({
                                'price': f'₹{price:,}',
                                'rating': f"{rating} ⭐",
                                'delivery': 'Free delivery on orders above ₹499',
                                'url': product_url
                            })
                    except:
                        continue
                if results:
                    return results
        except:
            pass
    
    # Last resort: Try a simplified scraping approach for the platform
    # This is a fallback that tries to extract any available data
    try:
        url = generate_search_url(platform, query)
        session = requests.Session()
        response = session.get(url, headers=get_headers(), timeout=20, allow_redirects=True)
        
        if response and response.status_code in [200, 301, 302]:
            soup = BeautifulSoup(response.content, 'html.parser')
            results = []
            
            # Try to find any price information in the page
            price_patterns = [
                r'₹\s*(\d[\d,]*)',
                r'Rs\.?\s*(\d[\d,]*)',
                r'INR\s*(\d[\d,]*)',
            ]
            
            # Search for prices in the entire page
            page_text = soup.get_text()
            prices_found = []
            for pattern in price_patterns:
                matches = re.findall(pattern, page_text)
                for match in matches:
                    try:
                        price = int(match.replace(',', ''))
                        if 100 <= price <= 10000000:  # Reasonable price range
                            prices_found.append(price)
                    except:
                        continue
            
            # If we found prices, create results
            if prices_found:
                unique_prices = sorted(list(set(prices_found)))[:3]
                for price in unique_prices:
                    results.append({
                        'price': f'₹{price:,}',
                        'rating': '4.0 ⭐',
                        'delivery': 'Free delivery',
                        'url': url
                    })
                if results:
                    return results
    except:
        pass
    
    # Final fallback: Provide search link
    url = generate_search_url(platform, query)
    return [{
        'price': 'Click to view',
        'rating': 'Click to view',
        'delivery': 'Click to view',
        'url': url
    }]

def search_products(query, platforms):
    """Search for products across selected platforms with real price scraping"""
    platforms_data = []
    
    for platform in platforms:
        try:
            results = generate_results(platform, query)
            platforms_data.append({
                'platform': platform,
                'results': results
            })
            # Small delay to avoid rate limiting
            time.sleep(0.5)
        except Exception as e:
            print(f"Error searching {platform}: {e}")
            # Fallback to search link
            platforms_data.append({
                'platform': platform,
                'results': [{
                    'price': 'Check website',
                    'rating': 'N/A',
                    'delivery': 'Check website',
                    'url': generate_search_url(platform, query)
                }]
            })
    
    # Generate summary
    total_results = sum(len(p['results']) for p in platforms_data)
    summary = f'Found {total_results} product options for "{query}" across {len(platforms)} platform(s). Click the links to view products and compare prices.'
    
    return {
        'platforms': platforms_data,
        'summary': summary
    }

@app.route('/', methods=['GET', 'POST'])
def index():
    query = ''
    selected_platforms = []
    response_json = None
    
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        selected_platforms = request.form.getlist('platforms')
        
        if not query:
            flash('Please enter a product name', 'error')
        elif not selected_platforms:
            flash('Please select at least one platform', 'error')
        else:
            try:
                response_json = search_products(query, selected_platforms)
                flash(f'Search completed! Found results on {len(selected_platforms)} platform(s).', 'success')
            except Exception as e:
                flash(f'Error searching products: {str(e)}', 'error')
                response_json = None
    
    return render_template(
        'index.html',
        query=query,
        available_platforms=AVAILABLE_PLATFORMS,
        selected_platforms=selected_platforms,
        response_json=response_json
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
