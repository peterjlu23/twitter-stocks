# StockTwitterApp
Program to retrieve 10 most recent tweets about stock.

### Installation:
1. Copy the repository to main.py on your local machine.
2. Obtain your Twitter API credentials. 
3. Replace the placeholders in the main.py file with your Twitter API credentials.
4. Create a requirements.txt file and copy the repository for pip installs. 
5. Run the main.py file using python main.py or just by clicking "Run".

### Usage:
Enter the stock symbol (without $) when prompted. 
If you want to search for another stock, press Enter.

### Filters:
The program filters out tweets that contain any of the following:
1. Banned words and hashtags commonly associated with spam or low-quality content.
2. Tweets from banned users who frequently post spam.
3. Specific emojis (🚀,📈,📉)
4. Retweets (excluding retweets with comments or quote tweets)
5. Tweets that are 80% similar to another tweet to remove duplicate content.
6. Tweets containing more than 5 $stock symbols.

### Output:
Program will show the 10 most recent tweets in this format:

 Date, Time
 Tweet_link
 @username: tweet_full_text
