import datetime
import json
import os
import platform
import re
import sqlite3
import time
import traceback
from contextlib import closing

import praw
import prawcore
import requests

import bot_responses
from keep_alive import keep_alive


def post_to_pastebin(title, body):
    """
    Uploads the text to PasteBin and returns the url of the Paste

    :param title: Title of the Paste
    :param body: Body of Paste
    :return: url of Paste
    """
    login_data = {
        'api_dev_key': os.getenv('pb_api_key'),
        'api_user_name': os.getenv('pb_username'),
        'api_user_password': os.getenv('pb_password')
    }

    data = {
        'api_option': 'paste',
        'api_dev_key': os.getenv('pb_api_key'),
        'api_paste_code': body,
        'api_paste_name': title,
        'api_paste_expire_date': '1W',
        'api_user_key': None,
        'api_paste_format': 'python'
    }

    login = requests.post("https://pastebin.com/api/api_login.php", data=login_data)
    login.raise_for_status()
    data['api_user_key'] = login.text

    r = requests.post("https://pastebin.com/api/api_post.php", data=data)
    r.raise_for_status()
    return r.text


def send_message_to_discord(message_param):
    """
    Sends the message to discord channel via webhook url

    :param message_param: message content
    """
    data = {"content": message_param, "username": "Karma Transfer Bot"}
    output = requests.post(os.getenv('discord_webhooks'), data=json.dumps(data),
                           headers={"Content-Type": "application/json"})
    output.raise_for_status()


def assign_flair(karma_value, author_name, fallout76marketplace):
    """
    Assigns user flair to a user based on the karma value

    :param karma_value: The amount of karma user has
    :param author_name: The name of the user
    :param fallout76marketplace: Subreddit in which the flair will be assigned
    :return: None
    """
    user_flair = f'Karma: {karma_value}'
    if karma_value < 49:
        fallout76marketplace.flair.set(author_name, text=user_flair, flair_template_id=ZERO_TO_FIFTY_FLAIR)
    elif 50 <= karma_value < 99:
        fallout76marketplace.flair.set(author_name, text=user_flair, flair_template_id=FIFTY_TO_HUNDRED_FLAIR)
    else:
        fallout76marketplace.flair.set(author_name, text=user_flair, flair_template_id=ABOVE_HUNDRED_FLAIR)


def transfer_karma(comment, submission, fallout76marketplace):
    author_name = comment.author.name
    cursor = karma_transfer_db.cursor()
    current_date_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %I:%M %p UTC')
    if submission.author_flair_text is None:
        bot_responses.no_karma_on_market76(comment)
        return None

    cursor.execute(f"SELECT * from karma_transfer_history WHERE author_name='{comment.author.name}'")
    result = cursor.fetchone()
    if result is not None:
        bot_responses.already_transferred(comment, result)
        return None

    # Get karma from market 76
    user_flair = submission.author_flair_text.split()
    our_karma = 0
    m76_karma = None
    # Check every element in flair if int is found break the loop
    for item in user_flair:
        try:
            m76_karma = int(item)
            break
        except ValueError:
            pass
    if m76_karma is None:
        bot_responses.something_went_wrong(comment, "r/Market76")
        return None

    # Get karma from Fallout76Marketplace
    user_flair = comment.author_flair_text
    if user_flair is not None:
        if "Karma:" in user_flair:
            try:
                user_flair = comment.author_flair_text.split()
                our_karma = int(user_flair[-1])
            except ValueError or AttributeError:
                bot_responses.something_went_wrong(comment, "r/Fallout76Marketplace")
                return None

    total_karma = m76_karma + our_karma
    assign_flair(karma_value=total_karma, author_name=author_name, fallout76marketplace=fallout76marketplace)
    url = 'https://www.reddit.com{}'.format(comment.permalink)
    cursor.execute(f"INSERT INTO karma_transfer_history VALUES ('{current_date_time}', "
                   f"'{author_name}', '{m76_karma}', '{url}')")

    karma_transfer_db.commit()
    cursor.close()
    bot_responses.transfer_successful(comment, m76_karma, total_karma)
    return None


def check_comments(comment, market76, fallout76marketplace):
    """
    Checks the comment body for the xferkarma commands and execute it accordingly

    :param comment: Praw comment object
    :param market76: Subreddit object
    :param fallout76marketplace: Subreddit in which the flair will be assigned
    """
    comment_body = comment.body.lower().strip()
    if re.search(r'^(xferkarma!|!xferkarma)$', comment_body, re.IGNORECASE):
        author = comment.author
        submissions = author.submissions.new(limit=None)
        for submission in submissions:
            if submission.subreddit == market76:
                transfer_karma(comment, submission, fallout76marketplace)
                break
        else:
            bot_responses.no_submission_found(comment)
    elif result := re.search(r'^(xferkarma info [A-Za-z0-9_-]+)$', comment_body, re.IGNORECASE):
        with closing(karma_transfer_db.cursor()) as cursor:
            cursor.execute("SELECT * from karma_transfer_history WHERE author_name=?", (result.group(1).split()[-1],))
            row = cursor.fetchone()
        bot_responses.transfer_information(comment, row, result.group(1).split()[-1])


def main():
    # Creating table if it doesn't exist
    with closing(karma_transfer_db.cursor()) as cursor:
        cursor.execute("""CREATE TABLE IF NOT EXISTS karma_transfer_history (date TEXT, author_name TEXT, 
                                                                                        karma INTEGER, 
                                                                                        comment_url TEXT)""")
    karma_transfer_db.commit()

    # Logging into Reddit
    reddit = praw.Reddit(client_id=os.getenv("client_id"),
                         client_secret=os.getenv("client_secret"),
                         username=os.getenv("username"),
                         password=os.getenv("password"),
                         user_agent=f"{platform.platform()}:KarmaTransfer:1.0 (by u/is_fake_Account)")
    print("Bot is now live!", time.strftime('%I:%M %p %Z'))

    fallout76marketplace = reddit.subreddit("Fallout76Marketplace")
    market76 = reddit.subreddit("Market76")
    failed_attempt = 1
    comment_stream = fallout76marketplace.stream.comments(pause_after=-1, skip_existing=True)
    while True:
        try:
            for comment in comment_stream:
                if comment is None:
                    break
                check_comments(comment, market76, fallout76marketplace)
                failed_attempt = 1
        except KeyboardInterrupt:
            break
        except Exception as exp:
            tb = traceback.format_exc()
            try:
                url = post_to_pastebin(f"{type(exp).__name__}: {exp}", tb)
                send_message_to_discord(f"[{type(exp).__name__}: {exp}]({url})")
            except Exception as discord_exception:
                print(tb)
                print("\nError sending message to discord", str(discord_exception))

            # In case of server error pause for multiple of 5 minutes
            if isinstance(exp, (prawcore.exceptions.ServerError, prawcore.exceptions.RequestException)):
                print(f"Waiting {(300 * failed_attempt) / 60} minutes...")
                time.sleep(300 * failed_attempt)
                failed_attempt += 1

            comment_stream = fallout76marketplace.stream.comments(pause_after=-1, skip_existing=True)
    print("Bot has stopped!", time.strftime('%I:%M %p %Z'))


# Entry point
if __name__ == '__main__':
    ABOVE_HUNDRED_FLAIR = "0467e0de-4a4d-11eb-9453-0e4e6fcf2865"
    FIFTY_TO_HUNDRED_FLAIR = "2624bc6a-4a4d-11eb-8b7c-0e6968d78889"
    ZERO_TO_FIFTY_FLAIR = "3c680234-4a4d-11eb-8124-0edd2b620987"
    karma_transfer_db = sqlite3.connect('karma_transfer_history.db')
    keep_alive()
    main()
