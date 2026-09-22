from database import save_event

EVENTS = [
    {
        
    }
]

def seed_events():
    return sum(1 for e in EVENTS if save_event(e))
