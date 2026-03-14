// Add this composable function to ServerConfigurationScreen.kt
// Insert after the ConnectionTestResultCard function (around line 472)

@Composable
private fun SavedServerUrlsSection(
    savedUrls: List<String>,
    newServerUrl: String,
    validationError: String?,
    onNewUrlChange: (String) -> Unit,
    onAddUrl: () -> Unit,
    onRemoveUrl: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        // Add new server URL
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.Top,
        ) {
            OutlinedTextField(
                value = newServerUrl,
                onValueChange = onNewUrlChange,
                label = { Text("Add Server URL") },
                placeholder = { Text("192.168.1.100:8000") },
                modifier = Modifier.weight(1f),
                singleLine = true,
                isError = validationError != null,
                colors =
                    OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = MaterialTheme.colorScheme.primary,
                        cursorColor = MaterialTheme.colorScheme.primary,
                    ),
            )

            Button(
                onClick = onAddUrl,
                enabled = newServerUrl.isNotBlank(),
                colors =
                    ButtonDefaults.buttonColors(
                        containerColor = AuraPrimary,
                        contentColor = MaterialTheme.colorScheme.onPrimary,
                    ),
            ) {
                Text("Add")
            }
        }

        if (validationError != null) {
            Text(
                text = validationError,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }

        // List of saved URLs
        if (savedUrls.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = "Saved URLs (${savedUrls.size})",
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium),
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                )

                savedUrls.forEach { url ->
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.5f),
                        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.12f)),
                    ) {
                        Row(
                            modifier =
                                Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 16.dp, vertical = 12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = url,
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.weight(1f),
                            )

                            Button(
                                onClick = { onRemoveUrl(url) },
                                colors =
                                    ButtonDefaults.buttonColors(
                                        containerColor = MaterialTheme.colorScheme.error.copy(alpha = 0.15f),
                                        contentColor = MaterialTheme.colorScheme.error,
                                    ),
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                            ) {
                                Text("Delete", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }
        } else {
            Text(
                text = "No saved URLs yet. Add your home and college server IPs above.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                modifier = Modifier.padding(vertical = 8.dp),
            )
        }
    }
}

// Then add this call in the main ServerConfigurationScreen function
// After the "Current configuration" ServerConfigSectionCard (around line 281):

                    ServerConfigSectionCard(
                        title = "Saved Server URLs",
                        subtitle = "Manage multiple server IPs for auto-discovery (home, college, etc.)",
                        icon = Icons.Default.NetworkCheck,
                    ) {
                        SavedServerUrlsSection(
                            savedUrls = uiState.savedServerUrls,
                            newServerUrl = uiState.newServerUrl,
                            validationError = uiState.validationError,
                            onNewUrlChange = viewModel::setNewServerUrl,
                            onAddUrl = { viewModel.addServerUrl(uiState.newServerUrl) },
                            onRemoveUrl = viewModel::removeServerUrl,
                        )
                    }
