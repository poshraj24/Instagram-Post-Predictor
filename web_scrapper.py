import time
import csv
import json
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

        # Avoid detection
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option("useAutomationExtension", False)
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--start-maximized")

        # Initialize driver
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=self.options
        )

        # Remove webdriver property
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

    def navigate_to_insights(self):
        """
        Attempt to navigate to Professional Dashboard Content Insights.
        This may need adjustment based on Instagram's current UI.
        """
        try:
            # Try to find and click on the profile
            profile_link = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@href, '/')]//img[@alt]")
                )
            )
            profile_link.click()
            time.sleep(2)

            # Look for Professional Dashboard or Insights button
            insights_button = self.driver.find_element(
                By.XPATH,
                "//a[contains(text(), 'Professional dashboard')] | "
                "//button[contains(text(), 'Professional dashboard')] | "
                "//span[contains(text(), 'View professional dashboard')]",
            )
            insights_button.click()
            time.sleep(3)

            print("Navigated to Professional Dashboard")
            return True

        except (TimeoutException, NoSuchElementException) as e:
            print(f"Auto-navigation failed: {e}")
            print("Please navigate manually to Content Insights.")
            return False

    def scroll_to_load_posts(self, scroll_count=5, scroll_pause=2):
        """
        Scroll the page to load more posts.

        Args:
            scroll_count: Number of times to scroll
            scroll_pause: Seconds to wait between scrolls
        """
        print(f"Scrolling to load posts ({scroll_count} scrolls)...")

        for i in range(scroll_count):
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(scroll_pause)
            print(f"  Scroll {i + 1}/{scroll_count} complete")

    def extract_post_views(self):
        """
        Extract views data from post elements in Content Insights.

        Returns:
            List of dictionaries containing post data
        """
        posts_data = []
        image_counter = 1

        # These selectors may need adjustment based on Instagram's current structure
        # Common patterns for insights posts
        post_selectors = [
            # Pattern 1: Grid items with metrics
            "//div[contains(@class, 'x1lliihq')]//div[contains(@class, 'x1n2onr6')]",
            # Pattern 2: Content items in insights
            "//article//div[contains(@class, '_aagw')]",
            # Pattern 3: Generic post containers
            "//div[contains(@class, 'x1lliihq') and .//img]",
            # Pattern 4: Insights specific
            "//div[@role='button' and .//img]",
        ]

        posts_found = []

        # Try different selectors
        for selector in post_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                if elements:
                    posts_found = elements
                    print(f"Found {len(elements)} posts using selector pattern")
                    break
            except Exception:
                continue

        if not posts_found:
            # Fallback: Find all images that might be posts
            print("Using fallback method to find posts...")
            posts_found = self.driver.find_elements(
                By.XPATH, "//img[contains(@src, 'instagram') and @alt]"
            )

        print(f"\nProcessing {len(posts_found)} potential posts...")

        for element in posts_found:
            try:
                post_info = self._extract_single_post_data(element, image_counter)
                if post_info:
                    posts_data.append(post_info)
                    image_counter += 1

            except StaleElementReferenceException:
                print(f"  Element became stale, skipping...")
                continue
            except Exception as e:
                print(f"  Error extracting post: {e}")
                continue

        self.posts_data = posts_data
        return posts_data

    def _extract_single_post_data(self, element, image_counter):
        """
        Extract data from a single post element.

        Args:
            element: Selenium WebElement
            image_counter: Current image counter for labeling

        Returns:
            Dictionary with post data or None
        """
        post_data = {
            "label": f"image{image_counter}",
            "views": None,
            "likes": None,
            "comments": None,
            "shares": None,
            "saves": None,
            "image_src": None,
            "alt_text": None,
            "scraped_at": datetime.now().isoformat(),
        }

        # Try to get image source
        try:
            img = element.find_element(By.TAG_NAME, "img")
            post_data["image_src"] = img.get_attribute("src")
            post_data["alt_text"] = img.get_attribute("alt")
        except NoSuchElementException:
            # Element might be the image itself
            if element.tag_name == "img":
                post_data["image_src"] = element.get_attribute("src")
                post_data["alt_text"] = element.get_attribute("alt")

        # Skip if no image found
        if not post_data["image_src"]:
            return None

        # Look for metrics in nearby elements
        parent = element
        for _ in range(5):  # Search up to 5 levels up
            try:
                parent = parent.find_element(By.XPATH, "..")
                text_content = parent.text

                # Extract views (common patterns)
                views = self._extract_metric(
                    text_content, ["views", "view", "plays", "play"]
                )
                if views:
                    post_data["views"] = views

                # Extract likes
                likes = self._extract_metric(text_content, ["likes", "like"])
                if likes:
                    post_data["likes"] = likes

                # Extract comments
                comments = self._extract_metric(text_content, ["comments", "comment"])
                if comments:
                    post_data["comments"] = comments

                # Extract shares
                shares = self._extract_metric(text_content, ["shares", "share"])
                if shares:
                    post_data["shares"] = shares

                # Extract saves
                saves = self._extract_metric(text_content, ["saves", "save"])
                if saves:
                    post_data["saves"] = saves

                if post_data["views"]:
                    break

            except NoSuchElementException:
                break

        # Click on post to get detailed metrics if views not found
        if not post_data["views"]:
            post_data["views"] = self._get_views_from_detail(element)

        print(f"  {post_data['label']}: {post_data['views'] or 'N/A'} views")
        return post_data

    def _extract_metric(self, text, keywords):
        """
        Extract a metric value from text based on keywords.

        Args:
            text: Text to search in
            keywords: List of keywords to look for

        Returns:
            Extracted number as string or None
        """
        import re

        text_lower = text.lower()

        for keyword in keywords:
            # Pattern: "1,234 views" or "1.2K views" or "views 1,234"
            patterns = [
                rf"([\d,\.]+[KMB]?)\s*{keyword}",
                rf"{keyword}\s*([\d,\.]+[KMB]?)",
            ]

            for pattern in patterns:
                match = re.search(pattern, text_lower)
                if match:
                    return match.group(1).upper()

        return None

    def _get_views_from_detail(self, element):
        """
        Click on post to open detail view and extract views.

        Args:
            element: Post element to click

        Returns:
            Views count or None
        """
        try:
            # Store current URL
            current_url = self.driver.current_url

            # Click on the post
            self.driver.execute_script("arguments[0].click();", element)
            time.sleep(2)

            # Look for views in the detail overlay
            detail_text = self.driver.find_element(By.TAG_NAME, "body").text
            views = self._extract_metric(detail_text, ["views", "plays"])

            # Close the detail view (press Escape or click close)
            try:
                close_button = self.driver.find_element(
                    By.XPATH,
                    "//button[contains(@aria-label, 'Close')] | //svg[@aria-label='Close']/..",
                )
                close_button.click()
            except NoSuchElementException:
                # Press Escape key
                from selenium.webdriver.common.keys import Keys

                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)

            time.sleep(1)
            return views

        except Exception as e:
            print(f"    Could not get detail views: {e}")
            return None

    def save_to_csv(self, filename="instagram_insights.csv"):
        """
        Save scraped data to CSV file.

        Args:
            filename: Output CSV filename
        """
        if not self.posts_data:
            print("No data to save!")
            return

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.posts_data[0].keys())
            writer.writeheader()
            writer.writerows(self.posts_data)

        print(f"\nData saved to {filename}")

    def save_to_json(self, filename="instagram_insights.json"):
        """
        Save scraped data to JSON file.

        Args:
            filename: Output JSON filename
        """
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
        print("\nPost Views:")
        print("-" * 30)

        for post in self.posts_data:
            views = post.get("views", "N/A")
            print(f"  {post['label']}: {views}")

    def close(self):
        """Close the browser."""
        self.driver.quit()
        print("\nBrowser closed.")


def main():
    """Main function to run the scraper."""
    print("=" * 50)
    print("Instagram Professional Dashboard Scraper")
    print("=" * 50)

    # Initialize scraper
    scraper = InstagramInsightsScraper(headless=False)

    try:
        # Open Instagram
        scraper.open_instagram()

        # Wait for manual login
        scraper.wait_for_manual_login()

        # Scroll to load more posts
        scraper.scroll_to_load_posts(scroll_count=3)

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
