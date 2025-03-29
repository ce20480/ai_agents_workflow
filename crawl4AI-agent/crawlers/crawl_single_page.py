import asyncio
import re

import tiktoken
from bs4 import BeautifulSoup

# from crawl4ai import *
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_filter_strategy import (
    BM25ContentFilter,
    PruningContentFilter,
    RelevantContentFilter,
)
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

# async def main():
#     async with AsyncWebCrawler() as crawler:
#         result = await crawler.arun(
#             url=input("Enter the URL to crawl: "),
#         )
#         # print(len(nltk.word_tokenize(result.markdown)))
#         if result.success:
#             return result.markdown

patterns = [
    # 1. Remove navigation bars (if they translate to consistent markdown headings/sections)
    r"^(#+) Navigation.*?(#+|$)", #Remove entire sections starting with '# Navigation'.
    r"^(#+) Top Menu.*?(#+|$)", #Remove entire sections starting with '# Top Menu'.
    r"^(#+) Header.*?(#+|$)", #Remove entire sections starting with '# Header'.

    # 2. Remove footers and copyright notices
    r"^.*?Copyright.*?\n?$", #Remove lines containing 'Copyright'.
    r"^(#+) Footer.*?(#+|$)", #Remove sections starting with '# Footer'.

    # 3. Remove sidebars and related product sections
    r"^(#+) Sidebar.*?(#+|$)", #Remove sections starting with '# Sidebar'.
    r"^(#+) Related Products.*?(#+|$)", #Remove sections starting with '# Related Products'.

    # 4. Remove social media links and buttons
    r"\[(Share on Facebook|Share on Twitter|Follow us on Instagram)\].*?\n", #Remove social media share links.
    r"(!\[.*?\]\((.*?facebook.com|twitter.com|instagram.com).*?\)).*?\n",#Remove image links for social media.

    # 5. Remove any call to action buttons, any discounts/offer related sections/links and promotional banners
    r"\[(Shop Now|Learn More|Add to Cart)\].*?\n", #Remove generic CTA links.
    r"^(#+) Special Offers.*?(#+|$)", #Remove 'Special Offers' sections.
    r"(<img.*?alt=.*?(Sale|Discount|Offer).*?>).*?\n", #Remove images with 'Sale', 'Discount', or 'Offer' in the alt text
    r"\[.*?(\d+% Off|BOGO|Free Shipping).*?\].*?\n",#Remove links containing common promotional phrases

    # 6. Remove disclaimers and legal notices (be very careful with this!)
    r"^.*?Disclaimer.*?\n?$", #Remove lines containing 'Disclaimer'.
    r"^.*?Terms and Conditions.*?\n?$", #Remove lines containing 'Terms and Conditions'.

    # 7. Clean up extra whitespace
    r"^\s*$\n",  # Remove blank lines
    r"\n{3,}", #Reduce multiple consecutive newlines to two.

    # 8. Remove script and style tag.
    r"<script.*?>[\s\S]*?<\/script>", # Remove javascript section from the text
    r"<style.*?>[\s\S]*?<\/style>" # Remove style section from the text
]


class PriceAndVariationsFilter(RelevantContentFilter):
    def filter_content(self, html, min_word_threshold=None):
        # 1) Parse the HTML with BeautifulSoup, lxml, or your parser of choice.
        soup = BeautifulSoup(html, "lxml")

        # 2) Remove all <script> and <style>, or known "boilerplate" nodes you never want
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.extract()

        # 3) Possibly also remove known ads or trackers by ID/class/regex
        for tag in soup.find_all(
            lambda t: any(
                x in (t.get("id") or "")
                for x in ["ad", "sponsored", "tracking", "promotion"]
            )
        ):
            tag.decompose()

        # 4) For each text block or node in the soup, check if it’s "interesting"
        #    i.e., something about pricing or variations
        relevant_blocks = []
        price_pattern = re.compile(r"\$\d+(?:\.\d{2})?")
        variation_keywords = ["size", "colour", "color", "variation", "option", "price"]

        # We can do a BFS or just do "find_all(text=True)" to extract lines
        for element in soup.find_all(text=True):
            text_str = element.strip()
            if not text_str:
                continue

            # a) Remove if it’s too short, e.g. less than 5 words
            words = text_str.split()
            if min_word_threshold and len(words) < min_word_threshold:
                continue

            # b) Check if it’s relevant: mention of price or variations
            if price_pattern.search(text_str.lower()):
                relevant_blocks.append(text_str)
            else:
                # Variation heuristics
                # e.g. text block has words about size or color
                has_variation_keyword = any(
                    kw in text_str.lower() for kw in variation_keywords
                )
                if has_variation_keyword:
                    relevant_blocks.append(text_str)

        # 5) Return the relevant text lines as a list
        return relevant_blocks


async def main(encoding):
    # 1) A BM25 filter with your custom query for "price" & synonyms
    bm25_filter = BM25ContentFilter(
        user_query="price",
        bm25_threshold=1.0,  # Adjust as needed
    )

    pruning_filter = PruningContentFilter(
        threshold=0.5, threshold_type="fixed", min_word_threshold=0
    )

    # 2) Or use your custom filter
    # custom_filter = PriceAndVariationsFilter()

    # 3) Attach it to the markdown generator
    # md_generator = DefaultMarkdownGenerator(content_filter=bm25_filter)
    # md_generator = DefaultMarkdownGenerator(content_filter=custom_filter)
    md_generator = DefaultMarkdownGenerator(content_filter=pruning_filter)

    config = CrawlerRunConfig(
        # markdown_generator=md_generator,
        # Possibly exclude standard tags that are never relevant to pricing:
        # excluded_tags=["nav", "style", "footer", "header", "script"],
        # excluded_tags=["nav", "footer", "header", "script"],
        # exclude_external_links=True,
    )
    num_tokens = 35000
    num_images = 99

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=input("Enter URL: "), config=config)
        if result.success:
            # This is your *filtered* or “fit” markdown, focusing on lines with price/cost
            markdown = result.markdown
            limited_markdown = result.markdown_v2.fit_markdown
            media = result.media["images"][:num_images]
            # print(len(limited_markdown))
            # print(limited_markdown)
            # print(markdown)
            # print(len(markdown))
            llm_markdown = encoding.decode(encoding.encode(markdown)[:num_tokens])
            print(llm_markdown)
            print(len(encoding.encode(limited_markdown)))
            print(len(encoding.encode(markdown)))
            print(media)

        else:
            print("Error:", result.error_message)


def parse_markdown(markdown):
    # Extract the text from the markdown
    text = re.sub(r"!\[.*?\]\(.*?\)", "", markdown)
    text = re.sub(r"\[.*?\]\(.*?\)", "", text)
    return text


def parse(md):
    lines = md.split("\n")

    relevant = []
    for idx, line in enumerate(lines):
        if re.search(
            r"(Style:|Variation:|Price:|\$\d+(\.\d+)?|USD\s*\d+)", line, re.IGNORECASE
        ):
            # Keep this line
            relevant.append(line)
            # Keep 1 line above + below for context if available
            # if idx > 0:
            #     relevant.append(lines[idx - 1])
            # if idx < len(lines) - 1:
            #     relevant.append(lines[idx + 1])
    filtered_text = "\n".join(set(relevant))  # or keep in order
    return filtered_text


def extract_product_price_blocks(text, product_name):
    """
    Extract lines referencing `product_name` and lines containing
    dollar-amount prices right after that product is found.
    Returns a list of tuples: [(line_of_product_name, price_line, price_list), ...].
    """
    lines = text.splitlines()

    # Regex pattern that captures typical US currency values, e.g. "$24.99", "$39", "$999.99"
    price_pattern = re.compile(r"\$\d+(?:\.\d+)?")

    # Will hold (product_line, price_line, [prices_found]) for each chunk
    extracted_data = []

    # Keep track if we are currently 'inside' the product block
    capturing = False
    current_product_line = None

    for line in lines:
        # 1) Check if line references the product name.
        if product_name in line:
            capturing = True
            current_product_line = line
            continue  # Move on to see if next lines contain a price

        if capturing:
            # 2) If the line includes a money value, parse out any prices:
            prices_found = price_pattern.findall(line)
            if prices_found:
                extracted_data.append((current_product_line, line, prices_found))

                # Optional: If you only want the FIRST price or the first line after product name,
                # you could break out here or do more logic.
                # For example:
                # capturing = False

    return extracted_data


def num_tokens_from_string(string: str, encoding_name: str) -> int:
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


def num_tokens_string_from_model(string: str, model: str) -> int:
    encoding = tiktoken.encoding_for_model(model)
    num_tokens = len(encoding.encode(string))
    return num_tokens


def token_to_string_from_model(token: int, model: str) -> str:
    encoding = tiktoken.encoding_for_model(model)
    string = encoding.decode([token])
    return string


def token_to_string_from_encoding(token: int, encoding: tiktoken.Encoding) -> str:
    string = encoding.decode([token])
    return string

def clean_markdown(markdown_text, patterns):
  """Applies a list of regex patterns to remove unwanted content from markdown."""
  for pattern in patterns:
    markdown_text = re.sub(pattern, '', markdown_text, flags=re.MULTILINE | re.DOTALL)
  return markdown_text

if __name__ == "__main__":
    # Select the tokenizer for your model (e.g., GPT-4 or GPT-3.5)
    # MODEL = "gpt-4o-mini"  # or "gpt-3.5-turbo", etc.
    MODEL = "gpt-4o-mini-2024-07-18"
    encoding = tiktoken.encoding_for_model(MODEL)
    # markdown = asyncio.run(main())
    asyncio.run(main(encoding))
    # print(markdown)
    # print(len(encoding.encode(markdown)))
    # with open("crawlers/text.txt", "r") as file:
    #     text = file.read()
    # print(num_tokens_string_from_model(text, MODEL))
    # raw_markdown_html = """(Paste your big raw HTML/Markdown text here)"""
    #
    # product_of_interest = "NATIONAL GEOGRAPHIC Break Open 10 Premium Geodes"
    # results = extract_product_price_blocks(raw_markdown_html, product_of_interest)
    #
    # # Print or further process the extracted lines
    # for prod_line, price_line, price_list in results:
    #     print("Product line:", prod_line)
    #     print("Price line:", price_line)
    #     print("Extracted prices:", price_list)
    #     print("----")
    # markdown = parse(markdown)
    # print(markdown)
    # print(len(encoding.encode(markdown)))
    # How to get sum of a list
