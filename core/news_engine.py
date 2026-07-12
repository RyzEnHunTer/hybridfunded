import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import pytz
import logging

logger = logging.getLogger("NewsEngine")

class NewsEngine:
    def __init__(self):
        import os
        self.news_events = []
        self.last_fetch_time = None
        self.cache_file = os.path.join(os.path.dirname(__file__), "news_cache.json")
        self.url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        # ForexFactory XML defaults to US/Eastern timezone
        self.ff_tz = pytz.timezone('US/Eastern')
        
        # Blackout configurations (in minutes)
        self.HIGH_IMPACT_PRE_MINS = 15
        self.HIGH_IMPACT_POST_MINS = 15
        
        self.update_news()

    def update_news(self):
        """Fetches and parses the latest XML news feed from ForexFactory."""
        now = datetime.now(timezone.utc)
        # Only fetch once per hour to avoid spamming the server
        if self.last_fetch_time and (now - self.last_fetch_time).total_seconds() < 3600:
            return

        try:
            req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()
                
            root = ET.fromstring(xml_data)
            events = []
            
            for event in root.findall('event'):
                title = event.find('title').text if event.find('title') is not None else "Unknown"
                country = event.find('country').text if event.find('country') is not None else ""
                date_str = event.find('date').text if event.find('date') is not None else ""
                time_str = event.find('time').text if event.find('time') is not None else ""
                impact = event.find('impact').text if event.find('impact') is not None else ""
                
                # Skip tentative or all-day events where time is not precise
                if not time_str or time_str.lower() in ["all day", "tentative"]:
                    continue
                    
                # Parse datetime (ForexFactory format: Date: MM-DD-YYYY, Time: HH:MMam/pm)
                try:
                    dt_str = f"{date_str} {time_str}"
                    # Example: 07-12-2026 8:30am
                    dt_obj = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                    # Localize to US/Eastern and convert to UTC
                    dt_aware = self.ff_tz.localize(dt_obj).astimezone(timezone.utc)
                    
                    events.append({
                        "title": title,
                        "currency": country.upper(),
                        "impact": impact.upper(),
                        "time_utc": dt_aware,
                        "time_str": dt_aware.strftime("%H:%M UTC"),
                        "date_str": dt_aware.strftime("%b %d")
                    })
                except Exception as e:
                    logger.debug(f"Failed to parse event time {dt_str}: {e}")
                    
            self.news_events = events
            self.last_fetch_time = now
            logger.info(f"📰 Successfully loaded {len(self.news_events)} scheduled news events.")
            
            # Save to cache
            import json
            try:
                cache_data = []
                for ev in self.news_events:
                    ev_copy = ev.copy()
                    ev_copy['time_utc'] = ev_copy['time_utc'].isoformat()
                    cache_data.append(ev_copy)
                with open(self.cache_file, "w") as f:
                    json.dump(cache_data, f)
            except Exception as e:
                logger.debug(f"Failed to save news cache: {e}")
            
        except Exception as e:
            logger.error(f"Failed to fetch ForexFactory calendar: {e}")
            self._load_from_cache()

    def _load_from_cache(self):
        import json
        import os
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    cache_data = json.load(f)
                
                events = []
                for ev in cache_data:
                    ev['time_utc'] = datetime.fromisoformat(ev['time_utc'])
                    events.append(ev)
                
                self.news_events = events
                logger.info(f"📰 Loaded {len(self.news_events)} news events from local cache due to API error.")
        except Exception as e:
            logger.error(f"Failed to load news from cache: {e}")

    def is_news_embargo_active(self, pair: str) -> bool:
        """
        Checks if the current UTC time is within a High-Impact news blackout window
        for the given currency pair.
        """
        self.update_news()
        
        if not self.news_events:
            return False
            
        now = datetime.now(timezone.utc)
        # Strip broker suffixes like .pro, .ecn, m, etc.
        import re
        clean_pair = re.sub(r'[.\-_].*$', '', pair)  # Remove everything after . - _
        clean_pair = clean_pair[:6]  # Take only first 6 chars (EURUSD)
        currencies_in_pair = [clean_pair[:3], clean_pair[3:6]]
        
        for event in self.news_events:
            if event["impact"] == "HIGH" and event["currency"] in currencies_in_pair:
                event_time = event["time_utc"]
                
                # Calculate the blackout window for this event
                embargo_start = event_time - timedelta(minutes=self.HIGH_IMPACT_PRE_MINS)
                embargo_end = event_time + timedelta(minutes=self.HIGH_IMPACT_POST_MINS)
                
                if embargo_start <= now <= embargo_end:
                    return True
                    
        return False
        
    def get_dashboard_schedule(self) -> list:
        """Returns a serialized list of HIGH impact news events for the Web Dashboard."""
        schedule = []
        for e in self.news_events:
            if e["impact"] == "HIGH":
                schedule.append({
                    "title": e["title"],
                    "currency": e["currency"],
                    "impact": e["impact"],
                    "time": e["time_str"],
                    "date": e["date_str"],
                    "timestamp": e["time_utc"].timestamp()
                })
            
        # Sort chronologically
        schedule.sort(key=lambda x: x["timestamp"])
        return schedule
