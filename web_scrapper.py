import time
import csv
import json
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from webdriver_manager.chrome import ChromeDriverManager


class InstagramInsightsScraper:
    """Scraper for Instagram Professional Dashboard Content Insights."""

    def __init__(self, headless=False):
        """
        Initialize the scraper with Chrome WebDriver.

        Args:
            headless: Run browser in headless mode (not recommended for login)
        """
        self.options = Options()
        if headless:
            self.options.add_argument("--headless")

        # Performance and compatibility options
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--start-maximized")
        self.options.add_argument("--disable-extensions")
        self.options.add_argument("--disable-popup-blocking")
        self.options.add_argument("--window-size=1920,1080")

        # Avoid detection
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option("useAutomationExtension", False)

        # Initialize driver
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=self.options)
        except Exception as e:
            print(f"webdriver-manager failed: {e}")
            print("Falling back to direct Chrome driver...")
            self.driver = webdriver.Chrome(options=self.options)

        self.driver.implicitly_wait(5)

        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        self.wait = WebDriverWait(self.driver, 20)
        self.posts_data = []

    def open_instagram(self):
        """Open Instagram login page."""
        self.driver.get("https://www.instagram.com/accounts/login/")
        print("Browser opened. Please log in to your Instagram account.")
        print(
            "After logging in, navigate to: Professional Dashboard > Content Insights"
        )

    def wait_for_manual_login(self):
        """Wait for user to complete manual login and navigation."""
        input(
            "\nPress ENTER after you've logged in and navigated to Content Insights..."
        )
        time.sleep(2)

    def scroll_to_load_all_posts(self, expected_posts=None, max_scrolls=50):
        """
        Scroll down to load all posts using lazy loading.

        Args:
            expected_posts: Expected number of posts (optional, for progress tracking)
            max_scrolls: Maximum number of scroll attempts
        """
        print(f"\nScrolling to load all posts...")
        if expected_posts:
            print(f"Expected posts: {expected_posts}")

        last_height = self.driver.execute_script("return document.body.scrollHeight")
        scroll_count = 0
        no_change_count = 0

        while scroll_count < max_scrolls:
            # Scroll down
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            scroll_count += 1

            # Wait for content to load
            time.sleep(1.5)

            # Calculate new scroll height
            new_height = self.driver.execute_script("return document.body.scrollHeight")

            # Check current number of posts loaded
            current_posts = self._count_visible_posts()
            print(f"  Scroll {scroll_count}: {current_posts} posts loaded...")

            # Check if we've reached the bottom
            if new_height == last_height:
                no_change_count += 1
                if no_change_count >= 3:  # No change for 3 scrolls
                    print(f"  Reached bottom of page after {scroll_count} scrolls")
                    break
            else:
                no_change_count = 0

            last_height = new_height

            # If we have expected_posts and reached it, stop
            if expected_posts and current_posts >= expected_posts:
                print(f"  Loaded all {expected_posts} expected posts")
                break

        # Scroll back to top
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        print(f"Scrolling complete. Total scrolls: {scroll_count}")

    def _count_visible_posts(self):
        """Count the number of post elements currently loaded."""
        try:
            # Try to count images in the grid
            images = self.driver.find_elements(
                By.XPATH,
                "//img[contains(@src, 'cdninstagram') or contains(@src, 'instagram')]",
            )
            return len(images)
        except:
            return 0

    def extract_post_views(self):
        """
        Extract views data from post elements in Content Insights.
        Handles numbers like: 50, 4.4K, 3.5K, 1.2M, etc.

        Returns:
            List of dictionaries containing post data
        """
        posts_data = []

        print("\n" + "=" * 50)
        print("EXTRACTING POST VIEW COUNTS")
        print("=" * 50)

        # Use JavaScript to extract ALL numbers with their positions
        # This handles: 50, 100, 4.4K, 3.5K, 1.2M, etc.
        js_script = """
        const results = [];
        
        // Get all text-containing elements
        const allElements = document.querySelectorAll('span, div, p');
        
        allElements.forEach(el => {
            // Get direct text content only (not nested)
            let text = '';
            for (let node of el.childNodes) {
                if (node.nodeType === Node.TEXT_NODE) {
                    text += node.textContent;
                }
            }
            text = text.trim();
            
            // Also check el.innerText if direct text is empty
            if (!text && el.children.length === 0) {
                text = el.innerText.trim();
            }
            
            if (!text) return;
            
            // Match patterns:
            // - Plain numbers: 50, 100, 1000
            // - Decimal with K/M/B: 4.4K, 3.5K, 1.2M, 2.5B
            // - Plain with K/M/B: 100K, 50M
            const pattern = /^(\d+\.?\d*)\s*([KMBkmb])?$/;
            const match = text.match(pattern);
            
            if (match) {
                const rect = el.getBoundingClientRect();
                
                // Must be visible and in reasonable position
                if (rect.width > 0 && rect.height > 0 && 
                    rect.top > 50 && rect.top < 10000 &&
                    rect.left > 0 && rect.left < 2000) {
                    
                    results.push({
                        text: text,
                        top: rect.top + window.scrollY,  // Absolute position
                        left: rect.left,
                        width: rect.width,
                        height: rect.height
                    });
                }
            }
        });
        
        return results;
        """

        # First, scroll through the entire page to get all positions
        print("Collecting all numbers from the page...")

        all_numbers = []

        # Get page height
        total_height = self.driver.execute_script("return document.body.scrollHeight")
        viewport_height = self.driver.execute_script("return window.innerHeight")

        # Scroll and collect numbers
        scroll_position = 0
        while scroll_position < total_height:
            self.driver.execute_script(f"window.scrollTo(0, {scroll_position});")
            time.sleep(0.5)

            # Execute JS to get numbers at current scroll position
            numbers = self.driver.execute_script(js_script)
            all_numbers.extend(numbers)

            scroll_position += viewport_height - 100  # Overlap slightly

        # Scroll back to top
        self.driver.execute_script("window.scrollTo(0, 0);")

        print(f"Found {len(all_numbers)} total number elements")

        # Deduplicate based on position and value
        unique_numbers = []
        seen = set()

        for num in all_numbers:
            # Create unique key based on approximate position (grid of ~150px)
            grid_x = int(num["left"] // 150)
            grid_y = int(num["top"] // 150)
            key = f"{grid_x}_{grid_y}_{num['text']}"

            if key not in seen:
                seen.add(key)
                unique_numbers.append(num)

        print(f"After deduplication: {len(unique_numbers)} unique numbers")

        # Sort by position (top to bottom, left to right)
        # Group by rows (posts in same row have similar Y values)
        unique_numbers.sort(key=lambda x: (int(x["top"] // 200), x["left"]))

        # Filter to keep only likely view counts
        # View counts are typically shown once per post, in a specific size range
        view_counts = []
        seen_positions = set()

        for num in unique_numbers:
            # Skip very small or very large elements (likely not view counts)
            if num["width"] < 10 or num["width"] > 100:
                continue
            if num["height"] < 10 or num["height"] > 50:
                continue

            # Use a coarser grid for final deduplication (one number per ~250px cell)
            pos_key = f"{int(num['left'] // 250)}_{int(num['top'] // 250)}"

            if pos_key not in seen_positions:
                seen_positions.add(pos_key)
                view_counts.append(num)

        print(f"Filtered to {len(view_counts)} likely view counts")

        # If we still have too few, try a different approach
        if len(view_counts) < 10:
            print("\nTrying alternative extraction method...")
            view_counts = self._extract_with_xpath()

        # Create post data entries
        if view_counts:
            # Sort again to ensure correct order
            view_counts.sort(key=lambda x: (int(x["top"] // 200), x["left"]))

            print(f"\nExtracted {len(view_counts)} posts:")
            print("-" * 30)

            for i, num_data in enumerate(view_counts):
                post_data = {
                    "label": f"image{i + 1}",
                    "views": num_data["text"],
                    "likes": None,
                    "comments": None,
                    "shares": None,
                    "saves": None,
                    "image_src": None,
                    "alt_text": None,
                    "scraped_at": datetime.now().isoformat(),
                }
                posts_data.append(post_data)
                print(f"  {post_data['label']}: {num_data['text']} views")

        self.posts_data = posts_data
        return posts_data

    def _extract_with_xpath(self):
        """Alternative extraction using XPath directly."""
        print("Using XPath extraction...")

        results = []
        seen_positions = set()

        # Find all spans that might contain view counts
        # Pattern matches: numbers with optional decimal and K/M/B suffix
        try:
            # Get all spans
            spans = self.driver.find_elements(By.TAG_NAME, "span")
            print(f"Found {len(spans)} span elements")

            for span in spans:
                try:
                    text = span.text.strip()
                    if not text:
                        continue

                    # Check if it matches our pattern
                    if re.match(r"^\d+\.?\d*[KMBkmb]?$", text):
                        location = span.location
                        size = span.size

                        # Skip if not visible
                        if size["width"] <= 0 or size["height"] <= 0:
                            continue

                        # Skip if too small or too large
                        if size["width"] < 15 or size["width"] > 80:
                            continue

                        # Deduplicate by position
                        pos_key = f"{location['x'] // 200}_{location['y'] // 200}"

                        if pos_key not in seen_positions:
                            seen_positions.add(pos_key)
                            results.append(
                                {
                                    "text": text,
                                    "top": location["y"],
                                    "left": location["x"],
                                    "width": size["width"],
                                    "height": size["height"],
                                }
                            )

                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    continue

        except Exception as e:
            print(f"XPath extraction error: {e}")

        print(f"XPath found {len(results)} view counts")
        return results

    def save_to_csv(self, filename="instagram_insights.csv"):
        """Save scraped data to CSV file."""
        if not self.posts_data:
            print("No data to save!")
            return

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.posts_data[0].keys())
            writer.writeheader()
            writer.writerows(self.posts_data)

        print(f"\nData saved to {filename}")

    def save_to_json(self, filename="instagram_insights.json"):
        """Save scraped data to JSON file."""
        if not self.posts_data:
            print("No data to save!")
            return

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.posts_data, f, indent=2, ensure_ascii=False)

        print(f"Data saved to {filename}")

    def print_summary(self):
        """Print a summary of scraped data."""
        if not self.posts_data:
            print("\nNo data collected.")
            return

        print("\n" + "=" * 50)
        print("SCRAPING SUMMARY")
        print("=" * 50)
        print(f"Total posts scraped: {len(self.posts_data)}")
        print("\nFirst 10 posts:")
        print("-" * 30)

        for post in self.posts_data[:10]:
            print(f"  {post['label']}: {post.get('views', 'N/A')} views")

        if len(self.posts_data) > 10:
            print(f"  ... and {len(self.posts_data) - 10} more")

    def close(self):
        """Close the browser."""
        self.driver.quit()
        print("\nBrowser closed.")


def main():
    """Main function to run the scraper."""
    print("=" * 50)
    print("Instagram Professional Dashboard Scraper")
    print("=" * 50)

    # Ask user for expected number of posts
    try:
        expected_posts = input(
            "\nHow many posts do you have? (press Enter to skip): "
        ).strip()
        expected_posts = int(expected_posts) if expected_posts else None
    except ValueError:
        expected_posts = None

    # Initialize scraper
    scraper = InstagramInsightsScraper(headless=False)

    try:
        # Open Instagram
        scraper.open_instagram()

        # Wait for manual login
        scraper.wait_for_manual_login()

        # Scroll to load all posts
        scraper.scroll_to_load_all_posts(expected_posts=expected_posts)

        # Extract post views
        print("\nExtracting post data...")
        posts = scraper.extract_post_views()

        # Print summary
        scraper.print_summary()

        # Save data
        if posts:
            scraper.save_to_csv()
            scraper.save_to_json()

    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user.")

    except Exception as e:
        print(f"\nError during scraping: {e}")
        import traceback

        traceback.print_exc()

    finally:
        input("\nPress ENTER to close the browser...")
        scraper.close()


if __name__ == "__main__":
    main()
