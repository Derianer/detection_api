import asyncio
import aiohttp

async def main():
    async with aiohttp.ClientSession() as session:
        with aiohttp.MultipartWriter('form-data') as multipart:
            with open("taro_detection/img.jpg", "rb") as file:
                image_data = file.read()
                multipart.append("xceltic_spread", {"Content-Disposition": 'file_name=lalsls; name=\"spread\"'})
                multipart.append(image_data, {"Content-Disposition": 'form-data; name="image"; filename="1.jpg"'})
                multipart.append('853934', {"Content-Disposition": 'form-data; name=\"id\"'})
                async with session.post('http://localhost:8080/api/image/recognize', data=multipart, timeout=5) as resp:
                    print(resp.status)
                    print(await resp.text())


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
