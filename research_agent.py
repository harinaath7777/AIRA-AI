import re
import urllib.parse
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup
from scipy.spatial.distance import cosine
from sentence_transformers import SentenceTransformer
import numpy as np
import time

SEARCH_RESULTS=6
PASSAGES_PER_PAGE=4
EMBEDDING_MODEL= "sentence-transformers/all-MiniLM-L6-v2"
TOP_PASSAGES=5
SUMMARY_SENTENCES=3
TIMEOUT=8

"""
Search Query
      ↓
Create empty URL list
      ↓
Create DuckDuckGo object
      ↓
Search DuckDuckGo
      ↓
Get search results
      ↓
Take one result
      ↓
Get "href" URL
      ↓
Is "href" available?
   ↙          ↘
 YES          NO
  ↓            ↓
Use href    Get "url"
               ↓
          Is "url" available?
            ↙        ↘
          YES        NO
           ↓          ↓
        Use url     Skip result
           ↓          ↓
           └──────────┘
                 ↓
          Clean DDG URL
          (unwrap_ddg)
                 ↓
        Add URL to the list
                 ↓
        Are there more results?
            ↙          ↘
          YES          NO
           ↓            ↓
     Take next result   Return URLs
"""

def search_web(query, max_results=SEARCH_RESULTS):

    # Step 1: Create an empty list
    # Each entry is {"url": str, "title": str}
    results_with_meta = []

    # Step 2: Create DuckDuckGo search object
    ddgs = DDGS()

    # Step 3: Search DuckDuckGo
    try:
        results = ddgs.text(query, max_results=max_results)
    except Exception:
        return results_with_meta

    # Step 4: Go through each search result
    for result in results:

        # Step 5: Try to get the href URL
        url = result.get("href")

        # Step 6: If href does not exist,
        # try to get the normal URL
        if not url:
            url = result.get("url")

        # Step 7: If there is still no URL,
        # skip this result
        if not url:
            continue

        # Step 8: Remove DuckDuckGo redirect
        clean_url = unwrap_ddg(url)

        # Step 9: Get the title (if available)
        title = result.get("title", "")

        # Step 10: Add entry with url and title
        results_with_meta.append({"url": clean_url, "title": title})

    # Step 11: Return all results
    return results_with_meta


"""
URL
 ↓
Break URL into parts
(urlparse)
 ↓
Is it a DuckDuckGo URL?
 ↓
 ┌───────────────┐
 │               │
YES              NO
 ↓                ↓
Get query        Return
parameters       original URL
 ↓
Find "uddg"
 ↓
Does "uddg" exist?
 ↓
 ┌───────────────┐
 │               │
YES              NO
 ↓                ↓
Get first value  Return original URL
 ↓
Decode URL
(unquote)
 ↓
Return real URL
"""

def unwrap_ddg(url):

    try:

        # Step 1: Break the URL into parts
        parsed_url = urllib.parse.urlparse(url)

        # Step 2: Check if the URL belongs to DuckDuckGo
        if "duckduckgo.com" in parsed_url.netloc:

            # Step 3: Get the query parameters
            query_parameters = urllib.parse.parse_qs(parsed_url.query)

            # Step 4: Get the "uddg" value
            uddg_value = query_parameters.get("uddg")

            # Step 5: Check if "uddg" exists
            if uddg_value:

                # Step 6: Get the first value
                encoded_url = uddg_value[0]

                # Step 7: Decode the URL
                real_url = urllib.parse.unquote(encoded_url)

                # Step 8: Return the real URL
                return real_url

    except Exception:
        pass

    # If it is not a DuckDuckGo URL,
    # return the original URL
    return url

"""
URL
 ↓
requests.get()
 ↓
Download webpage
 ↓
Was request successful?
 ↓
Is it HTML?
 ↓
BeautifulSoup reads HTML
 ↓
Remove script/style/navigation/etc.
 ↓
Find <p> paragraphs
 ↓
Extract text
 ↓
Join paragraphs
 ↓
Clean extra spaces
 ↓
Return clean text

"""

def fetch_text(url,timeout=TIMEOUT):
    headers = {"User-Agent": "Mozilla/5.0(research agent)"}
    try:
        r=requests.get(url,timeout=timeout,
        headers=headers,
        allow_redirects=True)

        if r.status_code !=200:
            return ""

        ct=r.headers.get("content-type","")

        if "html" not in ct.lower():
            return ""

        soup=BeautifulSoup(r.text,"html.parser")
        
        unwanted_tags=["script","style","noscript","header","footer","svg","iframe","nav","aside"]

        for tag_name in unwanted_tags:
            tags=soup.find_all(tag_name)
            for tag in tags:
                tag.extract()
        
        paragraph_tags=soup.find_all("p")

        paragraphs=[]

        for paragraph_tag in paragraph_tags:
            paragraph=paragraph_tag.get_text(" ",strip=True)

            if paragraph:
                paragraphs.append(paragraph)
        
        text=" "

        for paragraph in paragraphs:

            text=text+paragraph+" "

        if text.strip():
            
            text=re.sub(
                r"\s+"," ",text
            )

            text=text.strip()

            return text

# fallback


        meta=soup.find(
            "meta",attrs={"name":"description"}
        )

        if not meta:
            meta=soup.find("meta",attrs={"property","og:description"})

        if meta:
            content=meta.get("content")
            if content:
                return content.strip()

        if soup.title:
            title=soup.title.string
            if title:
                return title.strip()
    
    except Exception:
        return ""
    return ""

# FALLBACK FLOWCHART 
"""
Could we extract <p> paragraphs?
        ↓
       NO
        ↓
Try <meta name="description">
        ↓
      Found?
    ↙       ↘
  YES        NO
   ↓          ↓
Return     Try og:description
              ↓
            Found?
          ↙       ↘
        YES        NO
         ↓          ↓
       Return    Try <title>
                    ↓
                  Found?
                ↙       ↘
              YES        NO
               ↓          ↓
             Return     return ""
"""

# chunk passage

"""
Long Text
   ↓
Split into Words
   ↓
Any Words?
   ↓ YES
Create Empty Chunks List
   ↓
Start i = 0
   ↓
Take max_words
   ↓
Make Chunk
   ↓
Add Chunk
   ↓
Move i Forward
   ↓
More Words?
   ├── YES → Repeat
   └── NO  → Return Chunks
"""
#Example for chunk passage
"""
So if there are 350 words and max_words = 120, the function creates:

Chunk 1 → words 1–120
Chunk 2 → words 121–240
Chunk 3 → words 241–350

Then it returns those 3 chunks.

"""
def chunk_passages(text,max_words=120):

    words=text.split()
    
    if not words:
        return []

    chunks=[]

    i=0

    while i<len(words):

        chunk=words[i : i+max_words]

        chunk_text=" ".join(chunk)

        chunks.append(chunk_text)

        i+=max_words
    
    return chunks

#split sentences

"""
                         START
                           │
                           ↓
                    Receive text
                           │
                           ↓
              Split text at sentence
                   endings (. ! ?)
                           │
                           ↓
                        parts
                           │
                           ↓
                 Create empty list
                    sentences
                           │
                           ↓
                  Take one part
                           │
                           ↓
                Remove extra spaces
                    using strip()
                           │
                           ↓
                  Is sentence empty?
                     /          \
                   YES           NO
                    │             │
                    ↓             ↓
                  Skip       Add sentence
                    │         to sentences
                    │             │
                    └──────┬──────┘
                           ↓
                  Are there more parts?
                     /            \
                   YES             NO
                    │               │
                    ↓               ↓
              Take next part   Return sentences
                    │
                    └───────────────┐
                                    │
                                    ↓
                            Repeat the loop
"""
# example
"""
So you give it: 
"Hello world. How are you? I'm fine."  

And it returns: 
[ "Hello world.",
 "How are you?",
 "I'm fine." ]
"""

def split_sentences(text):

    parts=re.split(r'(?<=[.!?])\s+',text)

    sentences=[]

    for part in parts:

        sentence=part.strip()

        if sentence:

            sentences.append(sentence)

    return sentences

"""
Simple example

Suppose the user asks:

query = "best machine learning algorithms"
# Step 1 — Search
urls = search_web(query)

Suppose the search returns:

URL 1 → example.com/ml
URL 2 → wikipedia.org/machine-learning
URL 3 → sklearn.org/algorithms

So:

urls = [
    "URL1",
    "URL2",
    "URL3"
]
#Step 2 — Create empty docs
docs = []

Currently:

docs = []
#Step 3 — First URL
u = "URL1"

Fetch it:

txt = fetch_text(u)

Suppose it returns a long article:

"Machine learning is a field of AI...
There are many algorithms...
Decision trees are..."

Because txt exists:

if not txt:

is false.

So we continue.

#Step 4 — Chunk the text
chunks = chunk_passages(
    txt,
    max_words=120
)

Suppose the article has 300 words.

We might get:

chunks[0] → words 1–120
chunks[1] → words 121–240
chunks[2] → words 241–300
# Step 5 — Take the allowed chunks
for c in chunks[:PASSAGES_PER_PAGE]:

Suppose:

PASSAGES_PER_PAGE = 2

Then we only take:

Chunk 1
Chunk 2

We don't take Chunk 3.

#Step 6 — Create a document

For the first chunk:

document = {
    "url": u,
    "passage": c
}

It becomes something like:

{
    "url": "URL1",
    "passage": "Machine learning is a field of AI..."
}

Then:

docs.append(document)

Now:

docs
 ↓
[
    {
        "url": "URL1",
        "passage": "Machine learning is..."
    }
]

The second chunk gets added too.

5. Then it moves to URL 2

Same process:

URL 2
 ↓
fetch_text()
 ↓
Get text
 ↓
chunk_passages()
 ↓
Take allowed chunks
 ↓
Create documents
 ↓
Add to docs

Then URL 3.

6. Final docs

After processing all URLs, you might have:

docs = [
    {
        "url": "URL1",
        "passage": "Machine learning is..."
    },
    {
        "url": "URL1",
        "passage": "Decision trees are..."
    },
    {
        "url": "URL2",
        "passage": "Machine learning..."
    },
    {
        "url": "URL2",
        "passage": "Supervised learning..."
    }
]

"""

"""

ShortResearchAgent flowchart
                    START
                      │
                      ↓
            Create ShortResearchAgent
                      │
                      ↓
              Load embedding model
                      │
                      ↓
                Call run(query)
                      │
                      ↓
                 Get user query
                      │
                      ↓
                Search the web
                      │
                      ↓
                 Get URLs
                      │
                      ↓
                Create docs = []
                      │
                      ↓
              ┌───────────────┐
              │  Take one URL │
              └───────┬───────┘
                      ↓
              fetch_text(URL)
                      │
                      ↓
              Did we get text?
                /           \
              NO             YES
              │               │
              ↓               ↓
          Skip URL      chunk_passages()
                              │
                              ↓
                     Get smaller chunks
                              │
                              ↓
                    Take each allowed chunk
                              │
                              ↓
                     Create document
                              │
                              ↓
                    Add document to docs
                              │
                              ↓
                    More chunks?
                     /       \
                   YES        NO # once the inner finishes the chunking process it process the chunks of next url 
                    │          │
                    └──────────┤
                               ↓
                         More URLs?
                          /       \
                        YES        NO
                         │          │
                         └──────────┘
                                    ↓
                              Are docs empty?
                               /          \
                             YES           NO
                             │              │
                             ↓              ↓
                    Print "No documents"   Continue
                             │
                             ↓
                      Return empty result
                    
"""

class ShortResearchAgent:

    # --------------------------------
    # INITIALIZE THE AGENT
    # --------------------------------

    def __init__(self, embed_model=EMBEDDING_MODEL):

        # Step 1: Print the embedding model being loaded
        print(
            f"Loading embedder: {embed_model}..."
        )

        # Step 2: Load the embedding model
        self.embedder = SentenceTransformer(
            embed_model
        )


    # --------------------------------
    # RUN THE RESEARCH
    # --------------------------------

    def run(self, query):

        # Step 3: Record the starting time
        start = time.time()


        # --------------------------------
        # SEARCH
        # --------------------------------

        # Step 4: Search the web
        urls = search_web(query)

        # Step 5: Print number of URLs found
        print(
            f"Found {len(urls)} urls."
        )


        # --------------------------------
        # FETCH AND CHUNK
        # --------------------------------

        # Step 6: Create an empty list
        docs = []

        # Step 7: Go through each URL
        for u in urls:

            # Step 8: Fetch webpage text
            txt = fetch_text(u)

            # Step 9: Check if text was fetched
            if not txt:
                continue

            # Step 10: Split webpage text into chunks
            chunks = chunk_passages(
                txt,
                max_words=120
            )

            # Step 11: Go through each chunk
            for c in chunks[:PASSAGES_PER_PAGE]:

                # Step 12: Create a document
                document = {
                    "url": u,
                    "passage": c
                }

                # Step 13: Add document to docs
                docs.append(
                    document
                )


        # --------------------------------
        # CHECK DOCUMENTS
        # --------------------------------

        # Step 14: Check if no documents were collected
        if not docs:

            # Step 15: Print message
            print(
                "No documents fetched."
            )

            # Step 16: Return empty result
            return {
                "query": query,
                "passages": [],
                "summary": ""
            }


        # --------------------------------
        # CREATE DOCUMENT EMBEDDINGS
        # --------------------------------

        # Step 17: Create an empty list
        passages = []

        # Step 18: Go through every document
        for doc in docs:

            # Step 19: Get passage text
            passage_text = doc["passage"]

            # Step 20: Add passage text
            passages.append(
                passage_text
            )

        # Step 21: Create embeddings for passages
        passage_embs = self.embedder.encode(
            passages,
            convert_to_numpy=True,
            show_progress_bar=False
        )

        # Step 22: Create embedding for query
        q_emb = self.embedder.encode(
            query,
            convert_to_numpy=True
        )


        # --------------------------------
        # COMPARE PASSAGES WITH QUERY
        # --------------------------------

        # Step 23: Create an empty list
        passage_sims = []

        # Step 24: Go through every passage embedding
        for e in passage_embs:

            # Step 25: Calculate similarity
            similarity = 1 - cosine(
                e,
                q_emb
            )

            # Step 26: Store similarity
            passage_sims.append(
                similarity
            )


        # --------------------------------
        # SELECT TOP PASSAGES
        # --------------------------------

        # Step 27: Sort passage indexes
        sorted_indexes = np.argsort(
            passage_sims
        )

        # Step 28: Reverse the indexes
        sorted_indexes = sorted_indexes[::-1]

        # Step 29: Take the best passages
        top_passage_idx = sorted_indexes[
            :TOP_PASSAGES
        ]

        # Step 30: Create empty list
        top_passages = []

        # Step 31: Go through best indexes
        for idx in top_passage_idx:

            # Step 32: Get corresponding document
            passage = docs[idx]
            passage["score"] = passage_sims[idx]


            # Step 33: Add passage
            top_passages.append(
                passage
            )


        # --------------------------------
        # SUMMARIZE
        # --------------------------------

        # Step 34: Create an empty list
        sentences = []

        # Step 35: Go through every top passage
        for tp in top_passages:

            # Step 36: Split passage into sentences
            passage_sentences = split_sentences(
                tp["passage"]
            )

            # Step 37: Go through every sentence
            for s in passage_sentences:

                # Step 38: Create sentence document
                sentence_document = {
                    "sent": s,
                    "url": tp["url"]
                }

                # Step 39: Add sentence document
                sentences.append(
                    sentence_document
                )


        # --------------------------------
        # CHECK SENTENCES
        # --------------------------------

        # Step 40: Check if sentences exist
        if not sentences:

            # Step 41: Create summary message
            summary = "No summary could be generated."

        else:

            # --------------------------------
            # CREATE SENTENCE EMBEDDINGS
            # --------------------------------

            # Step 42: Create empty list
            sent_texts = []

            # Step 43: Go through every sentence
            for s in sentences:

                # Step 44: Get sentence text
                sentence_text = s["sent"]

                # Step 45: Add sentence text
                sent_texts.append(
                    sentence_text
                )

            # Step 46: Create sentence embeddings
            sent_embs = self.embedder.encode(
                sent_texts,
                convert_to_numpy=True,
                show_progress_bar=False
            )


            # --------------------------------
            # COMPARE SENTENCES WITH QUERY
            # --------------------------------

            # Step 47: Create empty list
            sent_sims = []

            # Step 48: Go through every sentence embedding
            for e in sent_embs:

                # Step 49: Calculate similarity
                similarity = 1 - cosine(
                    e,
                    q_emb
                )

                # Step 50: Store similarity
                sent_sims.append(
                    similarity
                )


            # --------------------------------
            # SELECT BEST SENTENCES
            # --------------------------------

            # Step 51: Sort sentence indexes
            sorted_indexes = np.argsort(
                sent_sims
            )

            # Step 52: Reverse the indexes
            sorted_indexes = sorted_indexes[::-1]

            # Step 53: Take best sentences
            top_sent_idx = sorted_indexes[
                :SUMMARY_SENTENCES
            ]

            # Step 54: Create empty list
            chosen = []

            # Step 55: Go through best indexes
            for idx in top_sent_idx:

                # Step 56: Get corresponding sentence
                sentence = sentences[idx]

                # Step 57: Add sentence
                chosen.append(
                    sentence
                )


            # --------------------------------
            # REMOVE DUPLICATES
            # --------------------------------

            # Step 58: Create empty set
            seen = set()

            # Step 59: Create empty list
            lines = []

            # Step 60: Go through chosen sentences
            for s in chosen:

                # Step 61: Create duplicate-check key
                key = s["sent"].lower()[:80]

                # Step 62: Check duplicate
                if key in seen:
                    continue

                # Step 63: Remember key
                seen.add(
                    key
                )

                # Step 64: Add sentence and source
                line = (
                    f"{s['sent']} "
                    f"(Source: {s['url']})"
                )

                # Step 65: Add formatted line
                lines.append(
                    line
                )

            # Step 66: Join all summary lines
            summary = " ".join(
                lines
            )


        # --------------------------------
        # FINISH
        # --------------------------------

        # Step 67: Calculate elapsed time
        elapsed = time.time() - start

        # Step 68: Return final result
        return {
            "query": query,
            "passages": top_passages,
            "summary": summary,
            "time": elapsed
        }
#summary 
"""
TOP PASSAGES
                         ↓
              Create empty sentences
                         ↓
                 Take one passage
                         ↓
              Split passage into
                   sentences
                         ↓
                Take one sentence
                         ↓
             Store sentence + URL
                         ↓
                 More sentences?
                  /           \
                YES            NO
                 │              │
                 ↓              ↓
            Next sentence   More passages?
                              /       \
                            YES        NO
                             │          │
                             ↓          ↓
                       Next passage   Check sentences
                                         ↓
                              Are there sentences?
                                /           \
                              NO             YES
                              │               │
                              ↓               ↓
                       No summary       Get sentence text
                                              ↓
                                      Create embeddings
                                              ↓
                              Compare each sentence
                                  with query
                                              ↓
                                     Similarity scores
                                              ↓
                                  Sort by similarity
                                              ↓
                                   Highest first
                                              ↓
                                  Take best sentences
                                              ↓
                                   Remove duplicates
                                              ↓
                                  Add source URLs
                                              ↓
                                   Join sentences
                                              ↓
                                  Calculate elapsed time
                                              ↓
                                    RETURN RESULT
"""
# --------------------------------
# MAIN PROGRAM
# --------------------------------

if __name__ == "__main__":

    # Create the research agent
    agent = ShortResearchAgent()

    # Create the question
    q = "What causes urban heat islands and how can cities reduce them?"

    # Print the question
    print(
        f"Running query: {q}\n"
    )

    # Run the research
    out = agent.run(q)


    # --------------------------------
    # PRINT TOP PASSAGES
    # --------------------------------

    print(
        "\nTop passages:"
    )

    for p in out["passages"]:

        print(
            f"- score {p['score']:.3f} "
            f"src {p['url']}\n"
            f"  {p['passage'][:200]}...\n"
        )


    # --------------------------------
    # PRINT SUMMARY
    # --------------------------------

    print(
        "--- Extractive summary ---"
    )

    print(
        out["summary"]
    )

    print(
        "--------------------------"
    )


    # --------------------------------
    # PRINT TIME
    # --------------------------------

    print(
        f"\nDone in {out['time']:.1f}s"
    )

    