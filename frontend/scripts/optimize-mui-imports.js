/**
 * Utility script to help optimize Material-UI imports for better tree-shaking
 * This script analyzes files and suggests optimizations
 */

const fs = require('fs');
const path = require('path');

// Common Material-UI components that should be imported individually
const MUI_COMPONENTS = [
  'Box', 'Paper', 'Card', 'CardContent', 'CardActions', 'Typography', 'Button', 'IconButton',
  'TextField', 'Select', 'MenuItem', 'FormControl', 'InputLabel', 'Chip', 'Avatar',
  'Grid', 'Container', 'Stack', 'Divider', 'List', 'ListItem', 'ListItemText', 'ListItemIcon',
  'Table', 'TableBody', 'TableCell', 'TableContainer', 'TableHead', 'TableRow', 'TablePagination',
  'Dialog', 'DialogTitle', 'DialogContent', 'DialogActions', 'Modal', 'Popover', 'Menu',
  'AppBar', 'Toolbar', 'Tabs', 'Tab', 'Drawer', 'Accordion', 'AccordionSummary', 'AccordionDetails',
  'Alert', 'Snackbar', 'CircularProgress', 'LinearProgress', 'Skeleton', 'Backdrop',
  'Tooltip', 'Popper', 'ClickAwayListener', 'Portal', 'Fade', 'Grow', 'Slide', 'Zoom',
  'CssBaseline', 'ThemeProvider', 'styled', 'useTheme', 'alpha'
];

/**
 * Analyze a file for Material-UI import optimizations
 */
function analyzeMuiImports(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');
    
    const suggestions = [];
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      
      // Look for multi-line Material-UI imports
      if (line.includes('import {') && line.includes('@mui/material')) {
        // Single line import
        const match = line.match(/import\s*\{\s*([^}]+)\s*\}\s*from\s*'@mui\/material'/);
        if (match) {
          const components = match[1].split(',').map(c => c.trim());
          if (components.length > 3) {
            suggestions.push({
              type: 'optimize-single-line',
              line: i + 1,
              current: line,
              components: components,
            });
          }
        }
      } else if (line.includes('import {') && !line.includes('}')) {
        // Multi-line import start
        let j = i + 1;
        let fullImport = line;
        
        while (j < lines.length && !lines[j].includes('}')) {
          fullImport += '\n' + lines[j];
          j++;
        }
        
        if (j < lines.length) {
          fullImport += '\n' + lines[j];
          
          if (fullImport.includes('@mui/material')) {
            const match = fullImport.match(/import\s*\{\s*([\s\S]*?)\s*\}\s*from\s*'@mui\/material'/);
            if (match) {
              const components = match[1].split(',').map(c => c.trim().replace(/\s+/g, ' '));
              suggestions.push({
                type: 'optimize-multi-line',
                startLine: i + 1,
                endLine: j + 1,
                current: fullImport,
                components: components.filter(c => c.length > 0),
              });
            }
          }
        }
      }
    }
    
    return suggestions;
  } catch (error) {
    console.error(`Error analyzing file ${filePath}:`, error.message);
    return [];
  }
}

/**
 * Generate optimized import statements
 */
function generateOptimizedImports(components) {
  const imports = [];
  
  // Add comment
  imports.push('// Optimized Material-UI imports for better tree-shaking');
  
  // Generate individual imports
  components.forEach(component => {
    const cleanComponent = component.replace(/\s+as\s+\w+/, ''); // Remove aliases for path
    
    if (component.includes('ThemeProvider')) {
      imports.push(`import ThemeProvider from '@mui/material/styles/ThemeProvider';`);
    } else if (component.includes('styled')) {
      imports.push(`import { styled } from '@mui/material/styles';`);
    } else if (component.includes('useTheme')) {
      imports.push(`import { useTheme } from '@mui/material/styles';`);
    } else if (component.includes('alpha')) {
      imports.push(`import { alpha } from '@mui/material/styles';`);
    } else if (cleanComponent && MUI_COMPONENTS.includes(cleanComponent.trim())) {
      imports.push(`import ${component} from '@mui/material/${cleanComponent.trim()}';`);
    } else if (cleanComponent) {
      // Fallback for unknown components
      imports.push(`import ${component} from '@mui/material/${cleanComponent.trim()}';`);
    }
  });
  
  return imports.join('\n');
}

/**
 * Scan directory for files to optimize
 */
function scanDirectory(dirPath, extensions = ['.tsx', '.ts']) {
  const files = [];
  
  function walkDir(currentPath) {
    const items = fs.readdirSync(currentPath);
    
    for (const item of items) {
      const fullPath = path.join(currentPath, item);
      const stat = fs.statSync(fullPath);
      
      if (stat.isDirectory() && !item.startsWith('.') && item !== 'node_modules') {
        walkDir(fullPath);
      } else if (stat.isFile() && extensions.some(ext => item.endsWith(ext))) {
        files.push(fullPath);
      }
    }
  }
  
  walkDir(dirPath);
  return files;
}

/**
 * Main analysis function
 */
function analyzeProject() {
  console.log('🔍 Analyzing Material-UI imports for optimization opportunities...\n');
  
  const srcPath = path.join(__dirname, '../src');
  const files = scanDirectory(srcPath);
  
  let totalSuggestions = 0;
  const results = [];
  
  for (const file of files) {
    const suggestions = analyzeMuiImports(file);
    if (suggestions.length > 0) {
      totalSuggestions += suggestions.length;
      results.push({ file: path.relative(srcPath, file), suggestions });
    }
  }
  
  if (totalSuggestions === 0) {
    console.log('✅ All Material-UI imports are already optimized!');
    return;
  }
  
  console.log(`Found ${totalSuggestions} optimization opportunities:\n`);
  
  results.forEach(({ file, suggestions }) => {
    console.log(`📄 ${file}`);
    
    suggestions.forEach(suggestion => {
      if (suggestion.type === 'optimize-single-line') {
        console.log(`  Line ${suggestion.line}:`);
        console.log(`    Current: ${suggestion.current}`);
        console.log(`    Optimized:`);
        console.log(`    ${generateOptimizedImports(suggestion.components)}`);
      } else if (suggestion.type === 'optimize-multi-line') {
        console.log(`  Lines ${suggestion.startLine}-${suggestion.endLine}:`);
        console.log(`    Components: ${suggestion.components.length} found`);
        console.log(`    Optimized:`);
        console.log(`    ${generateOptimizedImports(suggestion.components)}`);
      }
      console.log('');
    });
  });
  
  console.log(`\n💡 Benefits of optimization:`);
  console.log(`   • Smaller bundle size through better tree-shaking`);
  console.log(`   • Faster builds with more precise dependencies`);
  console.log(`   • Better development experience with clearer imports`);
}

// Run if called directly
if (require.main === module) {
  analyzeProject();
}

module.exports = { analyzeMuiImports, generateOptimizedImports, scanDirectory };