from datetime import datetime
import pytz

def get_philippine_time():
    """
    Get the current time in Philippine timezone (Asia/Manila)
    
    Returns:
        datetime: Current datetime in Philippine timezone
    """
    philippine_tz = pytz.timezone('Asia/Manila')
    philippine_time = datetime.now(philippine_tz)
    return philippine_time

def format_philippine_time(format_string='%Y-%m-%d %H:%M:%S %Z'):
    """
    Get formatted Philippine time as string
    
    Args:
        format_string (str): strftime format string
        
    Returns:
        str: Formatted time string
    """
    ph_time = get_philippine_time()
    return ph_time.strftime(format_string)

def get_time_greeting():
    """
    Get appropriate greeting based on Philippine time
    
    Returns:
        str: Time-appropriate greeting
    """
    ph_time = get_philippine_time()
    hour = ph_time.hour
    
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 18:
        return "Good afternoon"
    else:
        return "Good evening"

def is_standard_weekday_business_hours():
    """
    Check if current Philippine time falls within standard weekday business hours
    (Monday–Friday, 8 AM–5 PM). This is an indicative default, not a guarantee.
    """
    ph_time = get_philippine_time()

    if ph_time.weekday() >= 5:
        return False

    if 8 <= ph_time.hour < 17:
        return True

    return False

# Example usage
if __name__ == "__main__":
    print(f"Current Philippine Time: {format_philippine_time()}")
    print(f"Greeting: {get_time_greeting()}")
    print(f"Business Hours: {is_standard_weekday_business_hours()}")