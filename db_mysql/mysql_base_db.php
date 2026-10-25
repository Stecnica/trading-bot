<?php
// Connessione DB
include ( 'mysql_base_db_configuration.php' );

try {
        $pdo = new PDO("mysql:host=$host;dbname=$dbname;charset=utf8mb4", $username, $password);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
        die("Errore di connessione al database: " . $e->getMessage());
}

/**
 * Funzione per eseguire query con parametri in modo sicuro
 * @param string $query - SQL con placeholder
 * @param array $params - Parametri associati
 * @return array|bool - Dati risultanti o false se errore
 */
function executeQuery($query, $params = []) {
        global $pdo;
        try {
                $stmt = $pdo->prepare($query);
                $stmt->execute($params);
                
                // Controlla se è una SELECT o un'operazione di scrittura
                if (stripos(trim($query), 'SELECT') === 0) {
                        return $stmt->fetchAll(PDO::FETCH_ASSOC);
                }
                return true; // INSERT, UPDATE, DELETE
        } catch (PDOException $e) {
                error_log("Errore SQL: " . $e->getMessage());
                return false;
        }
}
?>
