<?php
// Load environment variables (if any)
require_once 'config.php';

// Telegram Bot API Token
define('BOT_TOKEN', getenv('BOT_TOKEN') ?: '8253938305:AAFUdmflQn4avUjoleVERLr-YuuCAyCfURo');
define('API_URL', 'https://api.telegram.org/bot' . BOT_TOKEN . '/');

// Handle webhook setup
if (php_sapi_name() == 'cli') {
    if ($argc > 1 && $argv[1] == 'set-webhook') {
        $url = $argv[2] ?? '';
        if (!empty($url)) {
            setWebhook($url);
        } else {
            echo "Please provide webhook URL: php index.php set-webhook <url>\n";
        }
        exit;
    } elseif ($argc > 1 && $argv[1] == 'delete-webhook') {
        deleteWebhook();
        exit;
    }
}

// Main bot logic
$content = file_get_contents("php://input");
$update = json_decode($content, true);

if (!$update) {
    exit;
}

processUpdate($update);

function processUpdate($update) {
    if (isset($update["message"])) {
        processMessage($update["message"]);
    } elseif (isset($update["callback_query"])) {
        processCallbackQuery($update["callback_query"]);
    }
}

function processMessage($message) {
    $chatId = $message['chat']['id'];
    $text = $message['text'] ?? '';
    $firstName = $message['from']['first_name'] ?? 'User';
    
    // Load user data
    $users = loadUsers();
    $userId = $message['from']['id'];
    
    // Initialize user if not exists
    if (!isset($users[$userId])) {
        $users[$userId] = [
            'first_name' => $firstName,
            'state' => 'start',
            'properties' => []
        ];
        saveUsers($users);
    }
    
    $user = $users[$userId];
    
    // Handle commands
    if (strpos($text, '/') === 0) {
        $command = explode(' ', $text)[0];
        
        switch ($command) {
            case '/start':
                sendMessage($chatId, "🏠 Welcome to PropertyDeal Bot, $firstName!\n\nI can help you manage your property listings. Use /help to see available commands.");
                $users[$userId]['state'] = 'main';
                saveUsers($users);
                break;
                
            case '/help':
                sendMessage($chatId, "🤖 Available Commands:\n\n/add - List a new property\n/list - View your properties\n/search - Find properties\n/help - Show this help message");
                break;
                
            case '/add':
                sendMessage($chatId, "🏡 Let's add a new property!\n\nPlease provide details in this format:\n\nType, Location, Price, Description\n\nExample: House, New York, 500000, Beautiful 3-bedroom house with garden");
                $users[$userId]['state'] = 'adding_property';
                saveUsers($users);
                break;
                
            case '/list':
                listProperties($chatId, $userId);
                break;
                
            case '/search':
                sendMessage($chatId, "🔍 To search for properties, please specify the location:\n\nExample: search New York");
                $users[$userId]['state'] = 'searching';
                saveUsers($users);
                break;
                
            default:
                sendMessage($chatId, "❌ Unknown command. Use /help to see available commands.");
        }
    } else {
        // Handle text based on user state
        switch ($user['state']) {
            case 'adding_property':
                addProperty($chatId, $userId, $text);
                break;
                
            case 'searching':
                searchProperties($chatId, $text);
                break;
                
            default:
                sendMessage($chatId, "Hi $firstName! Use /help to see what I can do.");
        }
    }
}

function addProperty($chatId, $userId, $text) {
    $users = loadUsers();
    
    $parts = explode(',', $text);
    if (count($parts) < 4) {
        sendMessage($chatId, "❌ Please provide all details in the correct format:\n\nType, Location, Price, Description");
        return;
    }
    
    $type = trim($parts[0]);
    $location = trim($parts[1]);
    $price = trim($parts[2]);
    $description = trim($parts[3]);
    
    if (!is_numeric($price)) {
        sendMessage($chatId, "❌ Price must be a number. Please try again.");
        return;
    }
    
    $property = [
        'type' => $type,
        'location' => $location,
        'price' => (float)$price,
        'description' => $description,
        'date' => date('Y-m-d H:i:s')
    ];
    
    $users[$userId]['properties'][] = $property;
    $users[$userId]['state'] = 'main';
    saveUsers($users);
    
    sendMessage($chatId, "✅ Property added successfully!\n\nType: $type\nLocation: $location\nPrice: $$price\nDescription: $description");
}

function listProperties($chatId, $userId) {
    $users = loadUsers();
    $user = $users[$userId];
    
    if (empty($user['properties'])) {
        sendMessage($chatId, "You haven't listed any properties yet. Use /add to create your first listing.");
        return;
    }
    
    $message = "🏠 Your Properties:\n\n";
    foreach ($user['properties'] as $index => $property) {
        $message .= ($index + 1) . ". {$property['type']} in {$property['location']} - \${$property['price']}\n";
        $message .= "   {$property['description']}\n\n";
    }
    
    sendMessage($chatId, $message);
}

function searchProperties($chatId, $location) {
    $users = loadUsers();
    $results = [];
    $location = strtolower(trim($location));
    
    foreach ($users as $userId => $user) {
        if (!empty($user['properties'])) {
            foreach ($user['properties'] as $property) {
                if (strpos(strtolower($property['location']), $location) !== false) {
                    $results[] = [
                        'property' => $property,
                        'user' => $user
                    ];
                }
            }
        }
    }
    
    if (empty($results)) {
        sendMessage($chatId, "❌ No properties found in $location.");
        return;
    }
    
    $message = "🔍 Properties in $location:\n\n";
    foreach ($results as $index => $result) {
        $p = $result['property'];
        $message .= ($index + 1) . ". {$p['type']} - \${$p['price']}\n";
        $message .= "   {$p['description']}\n";
        $message .= "   Listed by: {$result['user']['first_name']}\n\n";
    }
    
    sendMessage($chatId, $message);
}

function processCallbackQuery($callbackQuery) {
    // Handle inline keyboard interactions if needed
    $chatId = $callbackQuery['message']['chat']['id'];
    $data = $callbackQuery['data'];
    
    answerCallbackQuery($callbackQuery['id'], "Processed");
}

function sendMessage($chatId, $text) {
    $url = API_URL . "sendMessage?chat_id=" . $chatId . "&text=" . urlencode($text);
    file_get_contents($url);
}

function answerCallbackQuery($callbackQueryId, $text) {
    $url = API_URL . "answerCallbackQuery?callback_query_id=" . $callbackQueryId . "&text=" . urlencode($text);
    file_get_contents($url);
}

function setWebhook($url) {
    $url = API_URL . "setWebhook?url=" . urlencode($url);
    $result = file_get_contents($url);
    echo "Webhook set: " . $result . "\n";
}

function deleteWebhook() {
    $url = API_URL . "deleteWebhook";
    $result = file_get_contents($url);
    echo "Webhook deleted: " . $result . "\n";
}

function loadUsers() {
    if (!file_exists('users.json')) {
        file_put_contents('users.json', '{}');
    }
    return json_decode(file_get_contents('users.json'), true) ?: [];
}

function saveUsers($users) {
    file_put_contents('users.json', json_encode($users, JSON_PRETTY_PRINT));
}