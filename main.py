import datetime
import json
import os
import platform
import re
import time
import traceback
from contextlib import closing

import praw
import prawcore
import psycopg2
import requests
import yaml
from psycopg2 import sql

import bot_responses


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


def is_mod(author, fallout76marketplace) -> bool:
    """
    Checks if the author is moderator or not
    :param author: The reddit instance which will be checked in the list of mods
    :param fallout76marketplace: The subreddit instance in which the moderators list is checked
    :return: True if author is moderator otherwise False
    """
    moderators_list = fallout76marketplace.moderator()
    if author in moderators_list:
        return True
    else:
        return False


# Checks if the author is mod
def is_mod_or_courier(author, fallout76marketplace):
    if author is None:
        return False
    moderators_list = fallout76marketplace.moderator()
    wiki = fallout76marketplace.wiki["custom_bot_config/courier_list"]
    yaml_format = yaml.safe_load(wiki.content_md)
    courier_list = [x.lower() for x in yaml_format['couriers']]
    if author in moderators_list:
        return True
    if author.name.lower() in courier_list:
        return True
    return False


def assign_flair(comment, flair_text_list, karma_tuple, awardee_redditor, fallout76marketplace):
    """
    Assigns user flair to a user based on the karma value

    :param comment: The comment object of PRAW
    :param flair_text_list: Flair text template that will be used
    :param karma_tuple: Tuple of fallout76marketplace and market76 karma
    :param awardee_redditor: The name of the user
    :param fallout76marketplace: Subreddit in which the flair will be assigned
    :return: None
    """
    user_flair = f"{' '.join(flair_text_list)} {sum(karma_tuple)}"
    if is_mod_or_courier(awardee_redditor, fallout76marketplace):
        fallout76marketplace.flair.set(awardee_redditor.name, text=user_flair,
                                       flair_template_id=MODS_AND_COURIERS_FLAIR)
    else:
        if sum(karma_tuple) < 49:
            fallout76marketplace.flair.set(awardee_redditor.name, text=user_flair,
                                           flair_template_id=ZERO_TO_FIFTY_FLAIR)
        elif 50 <= sum(karma_tuple) < 99:
            fallout76marketplace.flair.set(awardee_redditor.name, text=user_flair,
                                           flair_template_id=FIFTY_TO_HUNDRED_FLAIR)
        else:
            fallout76marketplace.flair.set(awardee_redditor.name, text=user_flair,
                                           flair_template_id=ABOVE_HUNDRED_FLAIR)

    url = f'https://www.reddit.com{comment.permalink}'
    current_date_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %I:%M %p UTC')
    with closing(psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')) as db_conn:
        with closing(db_conn.cursor()) as cursor:
            query = sql.SQL("INSERT INTO karma_transfer_history (date, author_name, karma, comment_url) "
                            "VALUES (%s, %s, %s, %s) ON CONFLICT (author_name) DO UPDATE SET "
                            "(date, author_name, karma, comment_url) = "
                            "(EXCLUDED.date, EXCLUDED.author_name, EXCLUDED.karma, EXCLUDED.comment_url)")
            cursor.execute(query, (current_date_time, awardee_redditor.name, karma_tuple[-1], url))
        db_conn.commit()


def transfer_karma(comment, m76_submission, fallout76marketplace):
    # If user has no flair we assume they have no karma as well
    author_name = comment.author.name
    if m76_submission.author_flair_text is None:
        bot_responses.no_karma_on_market76(comment)
        return None

    # Checking if user has already transferred karma
    with closing(psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')) as db_conn:
        with closing(db_conn.cursor()) as cursor:
            cursor.execute("SELECT * from karma_transfer_history WHERE author_name=%s", (author_name,))
            result = cursor.fetchone()

    if result is not None:
        bot_responses.already_transferred(comment, result)
        return None

    # Extracting karma value from the flair
    # Since the introduction of platform icons it is hard to tell with certainty where
    # the karma value is located in flair could be :pc: +23 Karma or +23 Karma
    m76_karma = 0
    user_flair = m76_submission.author_flair_text.split()
    for item in user_flair:
        try:
            m76_karma = int(item)
            break
        except ValueError:
            pass
    if not m76_karma:
        bot_responses.something_went_wrong(comment, "r/Market76")
        return None

    # Get karma from Fallout76Marketplace
    our_karma = 0
    user_flair = comment.author_flair_text
    if user_flair is not None:
        try:
            user_flair = user_flair.split()
            our_karma = int(user_flair[-1])
        except ValueError:
            bot_responses.something_went_wrong(comment, "r/Fallout76Marketplace")
            return None
        flair_text_list = user_flair[:-1]
    else:
        flair_text_list = ['Karma:']

    assign_flair(comment, flair_text_list, (our_karma, m76_karma), comment.author, fallout76marketplace)
    bot_responses.transfer_successful(comment, (our_karma, m76_karma))
    return None


def check_comments(comment, market76, fallout76marketplace):
    """
    Checks the comment body for the xferkarma commands and execute it accordingly

    :param comment: Praw comment object
    :param market76: Subreddit object
    :param fallout76marketplace: Subreddit in which the flair will be assigned
    """
    # De-escaping to add support for reddit fancy-pants editor
    comment_body = comment.body.lower().strip().replace("\\", "")
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
        if is_mod(comment.author, fallout76marketplace):
            with closing(psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')) as db_conn:
                with closing(db_conn.cursor()) as cursor:
                    cursor.execute("SELECT * from karma_transfer_history WHERE author_name~*%s",
                                   (result.group(1).split()[-1],))
                    row = cursor.fetchone()
                bot_responses.transfer_information(comment, row, result.group(1).split()[-1])
    elif result := re.search(r'^(setkarma [A-Za-z0-9_-]+) \d+$', comment_body, re.IGNORECASE):
        if is_mod(comment.author, fallout76marketplace):
            author_name = result.group(0).split()[-2]
            redditor = reddit.redditor(author_name)
            try:
                _ = redditor.fullname
                if any(reddit.subreddit('Fallout76Marketplace').banned(author_name)):
                    bot_responses.user_banned_from_subreddit(comment, author_name)
                else:
                    karma = int(result.group(0).split()[-1])

                    # If user already has a flair we want to make sure that everything besides karma value
                    # is preserved
                    current_flair = next(fallout76marketplace.flair(author_name))
                    if current_flair['user'] == redditor:
                        flair_text_list = current_flair['flair_text'].split()[:-1]
                        assign_flair(comment, flair_text_list, (karma,), redditor, fallout76marketplace)
                    else:
                        flair_text_list = ['Karma:']
                        assign_flair(comment, flair_text_list, (karma,), redditor, fallout76marketplace)
                    bot_responses.karma_assigned(comment, karma, author_name)
            except (AttributeError, prawcore.exceptions.NotFound):
                bot_responses.user_banned_or_not_found(comment, author_name)


def main():
    # Creating table if it doesn't exist
    with closing(psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')) as db_conn:
        with closing(db_conn.cursor()) as cursor:
            cursor.execute("""CREATE TABLE IF NOT EXISTS karma_transfer_history (date TEXT, author_name TEXT, 
                                                                                            karma INTEGER, 
                                                                                            comment_url TEXT)""")
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS author_name_index ON karma_transfer_history (author_name)")
        db_conn.commit()

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
    quit(0)


# Entry point
if __name__ == '__main__':
    ABOVE_HUNDRED_FLAIR = "0467e0de-4a4d-11eb-9453-0e4e6fcf2865"
    FIFTY_TO_HUNDRED_FLAIR = "2624bc6a-4a4d-11eb-8b7c-0e6968d78889"
    ZERO_TO_FIFTY_FLAIR = "3c680234-4a4d-11eb-8124-0edd2b620987"
    MODS_AND_COURIERS_FLAIR = "51524056-4a4d-11eb-814b-0e7b734c1fd5"

    # Logging into Reddit
    reddit = praw.Reddit(client_id=os.getenv("client_id"),
                         client_secret=os.getenv("client_secret"),
                         username=os.getenv("reddit_username"),
                         password=os.getenv("reddit_password"),
                         user_agent=f"{platform.platform()}:KarmaTransfer:2.0 (by u/is_fake_Account)")
    main()
