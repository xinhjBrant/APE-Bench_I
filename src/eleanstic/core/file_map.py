# Copyright (2025) Bytedance Ltd. and/or its affiliates.

"""
File Mapping Manager Module
Responsible for storing and retrieving file mapping relationships for each commit

Uses a compact binary format to store file mappings, reducing disk space usage.
Each file mapping record contains only relative path, file hash, and file type information.
"""
import os
import struct
import shutil
import hashlib
import traceback

class FileMapManager:
    """
    File Mapping Manager, responsible for storing and retrieving file mapping relationships for each commit
    
    Uses binary file-based storage instead of JSON to reduce disk space usage
    """
    def __init__(self, storage_dir="storage", maps_dir="file_maps"):
        """Initialize file mapping manager
        
        Args:
            storage_dir: File content storage directory
            maps_dir: File mapping storage directory
        """
        self.storage_dir = storage_dir
        self.maps_dir = maps_dir
        
        # Ensure directories exist
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(self.maps_dir, exist_ok=True)
    
    def get_map_path(self, commit_id):
        """Get mapping file path for specified commit
        
        Args:
            commit_id: Commit ID
            
        Returns:
            Complete path to the mapping file
        """
        return os.path.join(self.maps_dir, f"{commit_id}.bin")
    
    def store_file_mapping(self, commit_id, file_mappings):
        """Store commit file mappings, using binary format
        
        File format:
        - 4 bytes: Record count (unsigned int)
        - For each record:
            - 2 bytes: Path length (unsigned short)
            - 32 bytes: SHA-256 hash
            - 1 byte: File type (0: regular file, 1: symlink)
            - Variable length: Relative path string (UTF-8 encoded)
        
        Args:
            commit_id: Commit ID
            file_mappings: {relative_path: {"hash": file_hash, "type": file_type}}
            
        Returns:
            True on success, False on failure
        """
        map_path = self.get_map_path(commit_id)
        
        try:
            with open(map_path, 'wb') as f:
                # Write record count
                f.write(struct.pack('!I', len(file_mappings)))
                
                # Write each record
                for rel_path, file_info in file_mappings.items():
                    path_bytes = rel_path.encode('utf-8')
                    path_len = len(path_bytes)
                    
                    # Convert hash from hex string to binary
                    hash_bin = bytes.fromhex(file_info["hash"])
                    
                    # File type: 0 for regular file, 1 for symlink
                    file_type = 1 if file_info["type"] == "symlink" else 0
                    
                    # Write record header
                    f.write(struct.pack('!H32sB', path_len, hash_bin, file_type))
                    
                    # Write path string
                    f.write(path_bytes)
            
            return True
        except Exception as e:
            print(f"Failed to store file mapping: {traceback.format_exc()}")
            return False
    
    def get_file_mapping(self, commit_id):
        """Get commit file mappings, reading from binary format
        
        Args:
            commit_id: Commit ID
            
        Returns:
            File mapping dictionary, or empty dictionary if not found
        """
        map_path = self.get_map_path(commit_id)
        
        if os.path.exists(map_path):
            try:
                with open(map_path, 'rb') as f:
                    # Read record count
                    record_count_data = f.read(4)
                    if not record_count_data:
                        return {}
                    
                    record_count = struct.unpack('!I', record_count_data)[0]
                    
                    # Read all records
                    file_mappings = {}
                    for _ in range(record_count):
                        # Read record header
                        header_data = f.read(35)  # 2(path_len) + 32(hash) + 1(type) = 35 bytes
                        if not header_data or len(header_data) < 35:
                            break
                            
                        path_len, hash_bin, file_type = struct.unpack('!H32sB', header_data)
                        
                        # Read path string
                        path_data = f.read(path_len)
                        if not path_data or len(path_data) < path_len:
                            break
                            
                        rel_path = path_data.decode('utf-8')
                        
                        # Convert hash to hex string
                        file_hash = hash_bin.hex()
                        
                        # Convert file type
                        type_str = "symlink" if file_type == 1 else "regular"
                        
                        # Store in mapping dictionary
                        file_mappings[rel_path] = {
                            "hash": file_hash,
                            "type": type_str
                        }
                    
                    return file_mappings
            except Exception as e:
                print(f"Failed to read file mapping: {traceback.format_exc()}")
        
        return {}
    
    def get_storage_path(self, file_hash):
        """Get storage path based on file hash
        
        Args:
            file_hash: File content hash
            
        Returns:
            Complete path to the file in storage system
        """
        # Use first 4 digits of hash for two-level directory
        return os.path.join(self.storage_dir, file_hash[:2], file_hash[2:4], file_hash)
    
    def compute_file_hash(self, filepath):
        """Calculate file hash
        
        Args:
            filepath: File path
            
        Returns:
            SHA256 hash of the file
        """
        hasher = hashlib.sha256()
        
        if os.path.islink(filepath):
            # For symlinks, hash the target path
            target = os.readlink(filepath)
            hasher.update(target.encode())
        else:
            # For regular files, hash the content
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
                    
        return hasher.hexdigest()
    
    def restore_file(self, dest_path, file_hash, file_type):
        """Restore file from storage system
        
        Args:
            dest_path: Target file path
            file_hash: File hash
            file_type: File type ("regular" or "symlink")
            
        Returns:
            On success returns (True, message), on failure returns (False, error_message)
        """
        storage_path = self.get_storage_path(file_hash)
        
        if not os.path.exists(storage_path):
            return False, f"File does not exist in storage: {storage_path}"
        
        # Ensure target directory exists
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # If target already exists, delete it first
        if os.path.exists(dest_path):
            if os.path.islink(dest_path) or not os.path.isdir(dest_path):
                os.remove(dest_path)
        
        try:
            if file_type == "symlink":
                # Restore symlink
                with open(storage_path, 'r') as f:
                    link_target = f.read()
                os.symlink(link_target, dest_path)
            else:
                # Restore regular file
                shutil.copy2(storage_path, dest_path)
            return True, f"File restored successfully: {dest_path}"
        except Exception as e:
            return False, f"Failed to restore file {dest_path}: {traceback.format_exc()}"