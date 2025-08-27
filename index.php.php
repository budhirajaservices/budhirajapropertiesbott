<?php
// Check if users.json is writable
if (file_exists('users.json') && !is_writable('users.json')) {
    // Try to fix permissions
    chmod('users.json', 0777);
}

// Create users.json if it doesn't exist
if (!file_exists('users.json')) {
    file_put_contents('users.json', '{}');
    chmod('users.json', 0777);
}

// Rest of your code...
