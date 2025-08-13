import datetime
import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from TeraBoxDownloader import Var

class MongoDB:
    def __init__(self, uri, database_name):
        self.__client = AsyncIOMotorClient(uri)
        self.__db = self.__client[database_name]
        self.col = self.__db.users
        self.config = self.__db.config
  
    def new_user(self, id):
        return dict(
            id=int(id),
            join_date=datetime.date.today().isoformat(),
            caption=None,
            ban_status=dict(
                is_banned=False,
                ban_duration=0,
                banned_on=datetime.date.max.isoformat(),
                ban_reason=''
            )
        )
    
    async def add_user(self, id):
        user = self.new_user(id)
        await self.col.insert_one(user)

    async def is_user_exist(self, id):
        user = await self.col.find_one({'id': int(id)})
        return True if user else False

    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count   

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    async def get_all_users(self):
        all_users = self.col.find({})
        return all_users
      
db = MongoDB(Var.MONGO_URI, Var.DB_NAME)
