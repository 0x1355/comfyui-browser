from aiohttp import web
import json
from os import path
import os
import shutil
import zipfile
import io
from urllib.parse import unquote

from ..utils import get_target_folder_files, get_parent_path, get_info_filename, \
    image_extensions, video_extensions, white_extensions, log

# folder_path, folder_type
async def api_get_files(request):
    folder_path = request.query.get('folder_path', '')
    folder_type = request.query.get('folder_type', 'outputs')
    files = get_target_folder_files(folder_path, folder_type=folder_type)

    if files == None:
        return web.Response(status=404)

    return web.json_response({
        'files': files
    })


# filename, folder_path, folder_type
async def api_delete_file(request):
    json_data = await request.json()
    filename = json_data['filename']
    folder_path = json_data.get('folder_path', '')
    folder_type = json_data.get('folder_type', 'outputs')

    parent_path = get_parent_path(folder_type)
    target_path = path.join(parent_path, folder_path, filename)
    if not path.exists(target_path):
        return web.json_response(status=404)

    if path.isdir(target_path):
        shutil.rmtree(target_path)
    else:
        os.remove(target_path)
    info_file_path = get_info_filename(target_path)
    if path.exists(info_file_path):
        os.remove(info_file_path)

    return web.Response(status=201)


# filename, folder_path, folder_type, new_data: {}
async def api_update_file(request):
    json_data = await request.json()
    filename = json_data['filename']
    folder_path = json_data.get('folder_path', '')
    folder_type = json_data.get('folder_type', 'outputs')
    parent_path = get_parent_path(folder_type)

    new_data = json_data.get('new_data', None)
    if not new_data:
        return web.Response(status=400)

    new_filename = new_data['filename']
    notes = new_data['notes']

    old_file_path = path.join(parent_path, folder_path, filename)
    new_file_path = path.join(parent_path, folder_path, new_filename)

    if not path.exists(old_file_path):
        return web.Response(status=404)

    if new_filename and filename != new_filename:
        shutil.move(
            old_file_path,
            new_file_path
        )
        old_info_file_path = get_info_filename(old_file_path)
        if path.exists(old_info_file_path):
            new_info_file_path = get_info_filename(new_file_path)
            shutil.move(
                old_info_file_path,
                new_info_file_path
            )

    if notes:
        extra = {
            "notes": notes
        }
        info_file_path = get_info_filename(new_file_path)
        with open(info_file_path, "w", encoding="utf-8") as outfile:
            json.dump(extra, outfile)

    return web.Response(status=201)

# filename, folder_path, folder_type
async def api_view_file(request):
    folder_type = request.query.get("folder_type", "outputs")
    folder_path = request.query.get("folder_path", "")
    filename = request.query.get("filename", None)
    if not filename:
        return web.Response(status=404)

    parent_path = get_parent_path(folder_type)
    file_path = path.join(parent_path, folder_path, filename)

    if not path.exists(file_path):
        return web.Response(status=404)

    with open(file_path, 'rb') as f:
        media_file = f.read()

    content_type = 'application/json'
    file_extension = path.splitext(filename)[1].lower()
    if file_extension in image_extensions:
        content_type = f'image/{file_extension[1:]}'
    if file_extension in video_extensions:
        content_type = f'video/{file_extension[1:]}'

    return web.Response(
        body=media_file,
        content_type=content_type,
        headers={"Content-Disposition": f"filename=\"{filename}\""}
    )


# folder_path, folder_type
async def api_download_directory_zip(request):
    folder_type = request.query.get("folder_type", "outputs")
    folder_path = request.query.get("folder_path", "")

    # Handle potential double-encoding from proxies
    folder_path = unquote(folder_path)

    if '..' in folder_path:
        return web.Response(status=400, text="Invalid path")

    parent_path = get_parent_path(folder_type)
    target_path = path.join(parent_path, folder_path)

    log(f"download-zip: folder_type={folder_type}, folder_path={folder_path}, target_path={target_path}")

    if not path.exists(target_path):
        log(f"download-zip: path does not exist: {target_path}")
        return web.Response(status=404, text=f"Path not found: {folder_path}")

    if not path.isdir(target_path):
        log(f"download-zip: path is not a directory: {target_path}")
        return web.Response(status=404, text=f"Not a directory: {folder_path}")

    # Create zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(target_path):
            # Filter out hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for file in files:
                # Skip hidden files and files not in whitelist
                if file.startswith('.'):
                    continue
                ext = path.splitext(file)[1].lower()
                if ext not in white_extensions:
                    continue

                file_path = path.join(root, file)
                # Preserve directory structure relative to target_path
                arcname = path.relpath(file_path, target_path)
                zip_file.write(file_path, arcname)

    zip_buffer.seek(0)

    # Use the directory name for the zip filename
    dir_name = path.basename(folder_path) if folder_path else "download"
    zip_filename = f"{dir_name}.zip"

    return web.Response(
        body=zip_buffer.read(),
        content_type='application/zip',
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"'
        }
    )
