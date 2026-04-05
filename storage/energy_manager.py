import asyncio
from datetime import datetime
from typing import List, Dict, Any


class EnergyManager:
    def __init__(self, firestore_manager, cache_only: bool = False):
        self.fm = firestore_manager
        self.max_energy = 10
        self.energy_increment = 1
        self.cache_only = cache_only

    async def reenergize_user(self, fid: str, current_energy: int = None) -> bool:
        try:
            if current_energy is None:
                user = self.fm._users_cache.get(fid)
                if not user:
                    return False
                current_energy = user.get("energy", 0)

            if current_energy < self.max_energy:
                if self.cache_only:
                    user = self.fm._users_cache.get(fid)
                    if user is not None:
                        user["energy"] = min(current_energy + 1, self.max_energy)
                else:
                    from google.cloud import firestore as _fs
                    self.fm._cache_apply(fid, {"energy": _fs.Increment(1)})
                    await self.fm.db.collection(
                        self.fm.users_collection
                    ).document(fid).update({"energy": _fs.Increment(1)})
                return True

            return False

        except Exception as e:
            print(f"Error re-energizing user {fid}: {e}")
            return False

    async def reenergize_all_users(self) -> Dict[str, Any]:
        try:
            to_reenergize = [
                (fid, data.get("energy", 0))
                for fid, data in self.fm._users_cache.items()
                if data.get("energy", 0) < self.max_energy
            ]

            stats = {
                "timestamp": datetime.now().isoformat(),
                "total_users_checked": len(to_reenergize),
                "users_reenergized": 0,
                "errors": 0,
            }

            tasks = [self.reenergize_user(fid, current_energy=e) for fid, e in to_reenergize]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    stats["errors"] += 1
                elif result:
                    stats["users_reenergized"] += 1

            print(f"Re-energization complete: {stats}")
            return stats

        except Exception as e:
            print(f"Error in reenergize_all_users: {e}")
            return {"error": str(e)}
    
    def _get_next_quarter_hour(self) -> int:
        """
        Calculate seconds until next quarter hour (0, 15, 30, or 45 minutes)
        
        Returns:
            Number of seconds to wait
        """
        now = datetime.now()
        current_minute = now.minute
        current_second = now.second
        
        # Find next quarter hour
        quarter_hours = [0, 15, 30, 45]
        next_quarter = None
        
        for quarter in quarter_hours:
            if current_minute < quarter:
                next_quarter = quarter
                break
        
        # If no quarter found in current hour, next is 0 of next hour
        if next_quarter is None:
            minutes_to_wait = 60 - current_minute
            seconds_to_wait = minutes_to_wait * 60 - current_second
        else:
            minutes_to_wait = next_quarter - current_minute
            seconds_to_wait = minutes_to_wait * 60 - current_second
        
        return seconds_to_wait
    
    async def start_reenergization_loop(self):
        """
        Start infinite loop that re-energizes users at 0, 15, 30, and 45 minutes of each hour
        """
        mode = "cache-only" if self.cache_only else "cache+firestore"
        print(f"Starting re-energization loop [{mode}] (every quarter hour: :00, :15, :30, :45)...")
        
        while True:
            try:
                # Wait until next quarter hour
                wait_seconds = self._get_next_quarter_hour()
                next_time = datetime.now()
                next_time = next_time.replace(second=0, microsecond=0)
                next_minute = (next_time.minute // 15 + 1) * 15
                if next_minute == 60:
                    next_minute = 0
                
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Waiting {wait_seconds} seconds until next cycle...")
                await asyncio.sleep(wait_seconds)
                
                # Run re-energization
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running re-energization cycle...")
                await self.reenergize_all_users()
                
            except Exception as e:
                print(f"Error in re-energization loop: {e}")
                # Wait a bit before retrying to avoid rapid failures
                await asyncio.sleep(60)


if __name__ == "__main__":
    # from storage.firestore_client import FirestoreManager
    from firestore_client import FirestoreManager

    async def main():
        fm = FirestoreManager()
        em = EnergyManager(fm)
        await em.start_reenergization_loop()

    asyncio.run(main())

