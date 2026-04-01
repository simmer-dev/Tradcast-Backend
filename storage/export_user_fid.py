from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient
import asyncio
import json
from typing import List, Dict


class UserExporter:
    def __init__(self):
        """Initialize async Firestore client"""
        self.db: AsyncClient = firestore.AsyncClient(project="miniapp-479712")
        self.users_collection = "users"
    
    async def export_users_to_json(self, output_file: str = "users.json") -> List[Dict[str, str]]:
        """
        Export all users from Firestore to a JSON file
        
        Args:
            output_file: Name of the output JSON file (default: "users.json")
            
        Returns:
            List of user dictionaries with format [{fid: username}, ...]
        """
        try:
            # Get all users from the collection
            users_ref = self.db.collection(self.users_collection)
            docs = await users_ref.get()
            
            # Build the list of {fid: username} objects
            users_list = []
            for doc in docs:
                fid = doc.id
                data = doc.to_dict()
                username = data.get("username", "Unknown")
                
                users_list.append({fid: username})
            
            # Write to JSON file
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(users_list, f, indent=2, ensure_ascii=False)
            
            print(f"✓ Successfully exported {len(users_list)} users to {output_file}")
            return users_list
            
        except Exception as e:
            print(f"Error exporting users: {e}")
            return []


async def main():
    exporter = UserExporter()
    
    print("=== Exporting Users to JSON ===")
    users = await exporter.export_users_to_json("users.json")
    
    # Print preview of the data
    print(f"\nPreview (first 5 users):")
    for user in users[:5]:
        print(f"  {user}")
    
    print(f"\nTotal users exported: {len(users)}")


if __name__ == "__main__":
    asyncio.run(main())
