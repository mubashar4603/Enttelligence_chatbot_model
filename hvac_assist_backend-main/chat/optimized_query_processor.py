"""
Optimized Query Processor for Llama3 8B with Pinecone
Handles all query types: Regular, Analytical, and Comparative
Optimized for 16GB GPU/RAM and 8K context window
"""

import re
import logging
from typing import Dict, Any, List, Optional
from django.db.models import Count, Sum, Avg, Max, Min, Q, F, FloatField, ExpressionWrapper
from django.db.models.functions import ExtractHour, ExtractWeekDay
from movies.models import Movie

logger = logging.getLogger(__name__)


class OptimizedQueryProcessor:
    """
    Unified query processor that intelligently routes queries and generates
    natural, detailed responses for all query types.
    """
    
    def __init__(self, rag_service=None):
        """Initialize with RAG service"""
        from chat.rag_service import get_rag_service
        self.rag_service = rag_service or get_rag_service()
        
        # Query classification patterns
        self.analytical_patterns = {
            'count': r'(how many|total number|count|number of)',
            'sum': r'(sum of|total|aggregate|add up)',
            'average': r'(average|avg|mean|typical)',
            'comparison': r'(compare|comparison|versus|vs|difference between)',
            'top': r'(top \d+|best|highest|most|popular|cheapest|expensive)',
            'analysis': r'(analyze|breakdown|statistics|statistical|metrics)'
        }
        
        # Entity extraction patterns
        self.entity_patterns = {
            'genre': r'(horror|action|comedy|drama|sci-?fi|thriller|romance|documentary|animation|adventure|fantasy|crime|mystery|western|war|musical|biography|history|family|sport)',
            'rating': r'\b(G|PG|PG-13|R|NC-17|NR|Not Rated)\b',
            'format': r'(IMAX|3D|2D|4DX|Standard|Dolby|DBOX|ScreenX)',
            'theater_chain': r'\b(AMC|Regal|Cinemark|Cineplex|Marcus|Alamo Drafthouse|Harkins)\b',
            'state': r'\b(California|New York|Texas|Florida|Illinois|CA|NY|TX|FL|IL|PA|OH|GA|NC|MI)\b',
            'price': r'\$(\d+(?:\.\d{2})?)',
            'movie_title': r'["\']([^"\']+)["\']',
        }
    
    def classify_query(self, query: str) -> str:
        """
        Classify query into type for optimal routing.
        Returns: 'analytical', 'comparative', or 'conversational'
        """
        query_lower = query.lower()
        
        # Check for analytical keywords
        analytical_score = sum(
            1 for pattern in self.analytical_patterns.values()
            if re.search(pattern, query_lower)
        )
        
        # Check for comparison
        if re.search(self.analytical_patterns['comparison'], query_lower):
            return 'comparative'
        
        # If 2+ analytical keywords, it's analytical
        if analytical_score >= 2:
            return 'analytical'
        
        # Check for specific analytical triggers
        if any(re.search(pattern, query_lower) for pattern in 
               [self.analytical_patterns['count'], 
                self.analytical_patterns['sum'],
                self.analytical_patterns['top']]):
            return 'analytical'
        
        # Default to conversational (RAG)
        return 'conversational'
    
    def extract_entities(self, query: str) -> Dict[str, Any]:
        """Extract entities and filters from query"""
        entities = {}
        
        for entity_type, pattern in self.entity_patterns.items():
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                entities[entity_type] = match.group(1)
        
        return entities
    
    def build_database_filters(self, entities: Dict[str, Any]) -> Q:
        """Build Django Q objects from extracted entities"""
        filters = Q()
        
        if 'genre' in entities:
            filters &= Q(genre__iexact=entities['genre'])
        
        if 'rating' in entities:
            filters &= Q(rating__iexact=entities['rating'])
        
        if 'format' in entities:
            filters &= Q(screen_format__icontains=entities['format']) | \
                      Q(movie_format__icontains=entities['format'])
        
        if 'theater_chain' in entities:
            filters &= Q(circuit_name__icontains=entities['theater_chain'])
        
        if 'state' in entities:
            state_abbrev = {
                'California': 'CA', 'New York': 'NY', 'Texas': 'TX',
                'Florida': 'FL', 'Illinois': 'IL'
            }.get(entities['state'], entities['state'])
            filters &= Q(theater_state__iexact=state_abbrev)
        
        if 'movie_title' in entities:
            filters &= Q(title__icontains=entities['movie_title'])
        
        return filters
    
    def handle_analytical_query(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle analytical queries with database.
        Returns structured data with natural language explanation.
        """
        query_lower = query.lower()
        filters = self.build_database_filters(entities)
        queryset = Movie.objects.filter(filters) if filters else Movie.objects.all()
        
        # Determine analytical operation
        if re.search(self.analytical_patterns['count'], query_lower):
            return self._handle_count(query, queryset, entities)
        
        elif re.search(self.analytical_patterns['sum'], query_lower):
            return self._handle_sum(query, queryset, entities)
        
        elif re.search(self.analytical_patterns['average'], query_lower):
            return self._handle_average(query, queryset, entities)
        
        elif re.search(self.analytical_patterns['top'], query_lower):
            return self._handle_top(query, queryset, entities)
        
        elif re.search(self.analytical_patterns['analysis'], query_lower):
            return self._handle_analysis(query, queryset, entities)
        
        else:
            # Default: show relevant data
            return self._handle_list(query, queryset, entities)
    
    def _handle_count(self, query: str, queryset, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle count queries with natural response"""
        try:
            # Determine if counting unique movies or showtimes
            if 'movie' in query.lower() and 'showtime' not in query.lower():
                count = queryset.values('title').distinct().count()
                item_type = "unique movies"
            else:
                count = queryset.count()
                item_type = "showtimes"
            
            # Build natural language response
            filter_desc = self._describe_filters(entities)
            
            response = f"I found **{count:,} {item_type}**{filter_desc}."
            
            # Add context and details
            if count > 0:
                # Get sample data for context
                if count <= 10:
                    samples = list(queryset.values_list('title', flat=True).distinct()[:count])
                    response += f"\n\n**Complete list:**\n"
                    for i, title in enumerate(samples, 1):
                        response += f"{i}. {title}\n"
                
                elif count <= 100:
                    samples = list(queryset.values_list('title', flat=True).distinct()[:5])
                    response += f"\n\n**Some examples include:**\n"
                    for title in samples:
                        response += f"• {title}\n"
                    response += f"\n_Total of {count:,} {item_type} available._"
                
                else:
                    # For large counts, add more context
                    genre_dist = queryset.values('genre').annotate(
                        count=Count('id')
                    ).order_by('-count')[:3]
                    
                    response += f"\n\n**Distribution by genre:**\n"
                    for dist in genre_dist:
                        percentage = (dist['count'] / count) * 100
                        response += f"• {dist['genre']}: {dist['count']:,} ({percentage:.1f}%)\n"
                    
                    # Add format information
                    format_dist = queryset.values('screen_format').annotate(
                        count=Count('id')
                    ).order_by('-count')[:3]
                    
                    response += f"\n**Top formats:**\n"
                    for dist in format_dist:
                        percentage = (dist['count'] / count) * 100
                        response += f"• {dist['screen_format']}: {dist['count']:,} ({percentage:.1f}%)\n"
            
            else:
                response += "\n\nTry broadening your search criteria or check different filters."
            
            return {
                'type': 'analytical',
                'message': response,
                'data': {
                    'count': count,
                    'item_type': item_type,
                    'filters': entities
                }
            }
        
        except Exception as e:
            logger.error(f"Error in count query: {e}")
            return self._error_response(f"Unable to count: {str(e)}")
    
    def _handle_sum(self, query: str, queryset, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle sum/aggregation queries"""
        try:
            # Determine what to sum
            field_map = {
                'reserved': ('reserved', 'reserved seats'),
                'available': ('available', 'available seats'),
                'total seats': ('total_seats', 'total seats'),
                'capacity': ('total_seats', 'seating capacity'),
            }
            
            field_to_sum = None
            field_label = None
            
            for keyword, (field, label) in field_map.items():
                if keyword in query.lower():
                    field_to_sum = field
                    field_label = label
                    break
            
            if not field_to_sum:
                field_to_sum = 'reserved'
                field_label = 'reserved seats'
            
            # Calculate aggregations
            stats = queryset.aggregate(
                total=Sum(field_to_sum),
                average=Avg(field_to_sum),
                maximum=Max(field_to_sum),
                minimum=Min(field_to_sum),
                count=Count('id')
            )
            
            total = stats['total'] or 0
            avg = stats['average'] or 0
            max_val = stats['maximum'] or 0
            min_val = stats['minimum'] or 0
            count = stats['count']
            
            filter_desc = self._describe_filters(entities)
            
            # Build detailed response
            response = f"## Summary of {field_label.title()}{filter_desc}\n\n"
            
            response += f"Based on **{count:,} showtimes**, here's the breakdown:\n\n"
            response += f"📊 **Aggregate Statistics:**\n"
            response += f"• **Total {field_label}:** {total:,}\n"
            response += f"• **Average per showtime:** {avg:.1f}\n"
            response += f"• **Highest:** {max_val:,}\n"
            response += f"• **Lowest:** {min_val:,}\n\n"
            
            # Add context about capacity utilization if relevant
            if field_to_sum == 'reserved':
                total_capacity_stats = queryset.aggregate(
                    total_capacity=Sum('total_seats')
                )
                total_capacity = total_capacity_stats['total_capacity'] or 1
                occupancy_rate = (total / total_capacity) * 100 if total_capacity > 0 else 0
                
                response += f"📈 **Occupancy Analysis:**\n"
                response += f"• Total capacity: {total_capacity:,} seats\n"
                response += f"• Overall occupancy rate: **{occupancy_rate:.1f}%**\n"
                response += f"• Available seats: {total_capacity - total:,}\n\n"
            
            # Add top performers
            top_items = queryset.order_by(f'-{field_to_sum}')[:5]
            if top_items.exists():
                response += f"🎬 **Top 5 by {field_label}:**\n"
                for i, item in enumerate(top_items, 1):
                    value = getattr(item, field_to_sum)
                    response += f"{i}. **{item.title}** at {item.theater_name}\n"
                    response += f"   • {field_label.title()}: {value:,}\n"
                    if field_to_sum == 'reserved':
                        occupancy = (value / item.total_seats * 100) if item.total_seats > 0 else 0
                        response += f"   • Occupancy: {occupancy:.1f}%\n"
            
            return {
                'type': 'analytical',
                'message': response,
                'data': {
                    'total': float(total),
                    'average': float(avg),
                    'maximum': float(max_val),
                    'minimum': float(min_val),
                    'count': count,
                    'field': field_label,
                    'filters': entities
                }
            }
        
        except Exception as e:
            logger.error(f"Error in sum query: {e}")
            return self._error_response(f"Unable to calculate sum: {str(e)}")
    
    def _handle_average(self, query: str, queryset, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle average queries with comprehensive stats"""
        try:
            # Calculate multiple averages
            stats = queryset.aggregate(
                avg_price=Avg('price'),
                avg_seats=Avg('total_seats'),
                avg_reserved=Avg('reserved'),
                avg_available=Avg('available'),
                min_price=Min('price'),
                max_price=Max('price'),
                count=Count('id')
            )
            
            count = stats['count']
            filter_desc = self._describe_filters(entities)
            
            response = f"## Average Statistics{filter_desc}\n\n"
            response += f"Based on **{count:,} showtimes**, here's a comprehensive breakdown:\n\n"
            
            # Price statistics
            if stats['avg_price']:
                response += f"💰 **Pricing:**\n"
                response += f"• Average ticket price: **${stats['avg_price']:.2f}**\n"
                response += f"• Price range: ${stats['min_price']:.2f} - ${stats['max_price']:.2f}\n"
                response += f"• Price spread: ${stats['max_price'] - stats['min_price']:.2f}\n\n"
            
            # Seating statistics
            if stats['avg_seats']:
                occupancy_rate = (stats['avg_reserved'] / stats['avg_seats'] * 100) if stats['avg_seats'] > 0 else 0
                
                response += f"🪑 **Seating:**\n"
                response += f"• Average theater capacity: **{stats['avg_seats']:.0f} seats**\n"
                response += f"• Average reserved: {stats['avg_reserved']:.0f} seats\n"
                response += f"• Average available: {stats['avg_available']:.0f} seats\n"
                response += f"• Average occupancy rate: **{occupancy_rate:.1f}%**\n\n"
            
            # Add distribution by format
            format_stats = queryset.values('screen_format').annotate(
                avg_price=Avg('price'),
                count=Count('id')
            ).order_by('-count')[:5]
            
            if format_stats:
                response += f"🎥 **By Format:**\n"
                for fmt in format_stats:
                    response += f"• **{fmt['screen_format']}:** "
                    if fmt['avg_price']:
                        response += f"${fmt['avg_price']:.2f} avg"
                    response += f" ({fmt['count']:,} showtimes)\n"
            
            return {
                'type': 'analytical',
                'message': response,
                'data': stats
            }
        
        except Exception as e:
            logger.error(f"Error in average query: {e}")
            return self._error_response(f"Unable to calculate averages: {str(e)}")
    
    def _handle_top(self, query: str, queryset, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle top N queries"""
        try:
            # Extract number
            limit_match = re.search(r'top (\d+)', query.lower())
            limit = int(limit_match.group(1)) if limit_match else 10
            limit = min(limit, 50)  # Cap at 50
            
            # Determine sorting
            if 'expensive' in query.lower() or 'highest price' in query.lower():
                order_field = '-price'
                metric = 'most expensive'
            elif 'cheap' in query.lower() or 'lowest price' in query.lower():
                order_field = 'price'
                metric = 'cheapest'
            elif 'popular' in query.lower() or 'occupied' in query.lower():
                order_field = '-reserved'
                metric = 'most popular'
            elif 'available' in query.lower():
                order_field = '-available'
                metric = 'most seats available'
            else:
                # Default: by unique movie popularity
                movies = queryset.values('title', 'genre', 'rating').annotate(
                    showtime_count=Count('id'),
                    avg_price=Avg('price'),
                    total_reserved=Sum('reserved')
                ).order_by('-showtime_count')[:limit]
                
                return self._format_top_movies_response(movies, entities, limit)
            
            # Get top showtimes
            results = queryset.order_by(order_field)[:limit]
            
            filter_desc = self._describe_filters(entities)
            response = f"## Top {len(results)} {metric.title()} Showtimes{filter_desc}\n\n"
            
            for i, item in enumerate(results, 1):
                response += f"### {i}. {item.title}\n"
                response += f"**Theater:** {item.theater_name}, {item.theater_city}, {item.theater_state}\n"
                response += f"**Date & Time:** {item.date_sh.strftime('%B %d, %Y')} at {item.time_sh.strftime('%I:%M %p')}\n"
                response += f"**Format:** {item.screen_format} | **Rating:** {item.rating}\n"
                response += f"**Price:** ${item.price:.2f}\n"
                response += f"**Seating:** {item.reserved}/{item.total_seats} reserved "
                
                if item.total_seats > 0:
                    occupancy = (item.reserved / item.total_seats) * 100
                    response += f"({occupancy:.1f}% occupancy)"
                
                response += "\n\n"
            
            return {
                'type': 'analytical',
                'message': response,
                'data': {
                    'count': len(results),
                    'metric': metric,
                    'filters': entities
                }
            }
        
        except Exception as e:
            logger.error(f"Error in top query: {e}")
            return self._error_response(f"Unable to get top results: {str(e)}")
    
    def _format_top_movies_response(self, movies, entities, limit):
        """Format top movies by showtime count"""
        filter_desc = self._describe_filters(entities)
        response = f"## Top {len(movies)} Most Popular Movies{filter_desc}\n\n"
        response += "_Ranked by number of showtimes_\n\n"
        
        for i, movie in enumerate(movies, 1):
            response += f"### {i}. {movie['title']}\n"
            response += f"**Genre:** {movie['genre']} | **Rating:** {movie['rating']}\n"
            response += f"**Showtimes:** {movie['showtime_count']:,} screenings\n"
            if movie['avg_price']:
                response += f"**Average Price:** ${movie['avg_price']:.2f}\n"
            if movie['total_reserved']:
                response += f"**Total Attendance:** {movie['total_reserved']:,} seats reserved\n"
            response += "\n"
        
        return {
            'type': 'analytical',
            'message': response,
            'data': {
                'movies': list(movies),
                'count': len(movies),
                'filters': entities
            }
        }
    
    def _handle_analysis(self, query: str, queryset, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle complex analysis queries"""
        try:
            count = queryset.count()
            filter_desc = self._describe_filters(entities)
            
            response = f"# Comprehensive Analysis{filter_desc}\n\n"
            response += f"_Dataset: {count:,} showtimes_\n\n"
            
            # Overall statistics
            overall_stats = queryset.aggregate(
                total_capacity=Sum('total_seats'),
                total_reserved=Sum('reserved'),
                total_available=Sum('available'),
                avg_price=Avg('price'),
                min_price=Min('price'),
                max_price=Max('price'),
                unique_movies=Count('title', distinct=True),
                unique_theaters=Count('theater_name', distinct=True)
            )
            
            response += f"## 📊 Overall Statistics\n\n"
            response += f"• **Unique Movies:** {overall_stats['unique_movies']:,}\n"
            response += f"• **Theaters:** {overall_stats['unique_theaters']:,}\n"
            response += f"• **Total Capacity:** {overall_stats['total_capacity']:,} seats\n"
            response += f"• **Total Reserved:** {overall_stats['total_reserved']:,} seats\n"
            
            if overall_stats['total_capacity'] and overall_stats['total_capacity'] > 0:
                occupancy = (overall_stats['total_reserved'] / overall_stats['total_capacity']) * 100
                response += f"• **Overall Occupancy:** {occupancy:.1f}%\n"
            
            response += f"• **Average Price:** ${overall_stats['avg_price']:.2f}\n"
            response += f"• **Price Range:** ${overall_stats['min_price']:.2f} - ${overall_stats['max_price']:.2f}\n\n"
            
            # Genre breakdown
            genre_stats = queryset.values('genre').annotate(
                count=Count('id'),
                avg_price=Avg('price'),
                total_reserved=Sum('reserved')
            ).order_by('-count')[:10]
            
            response += f"## 🎬 Top Genres\n\n"
            for genre in genre_stats:
                percentage = (genre['count'] / count) * 100
                response += f"**{genre['genre']}:**\n"
                response += f"  • {genre['count']:,} showtimes ({percentage:.1f}%)\n"
                response += f"  • Avg price: ${genre['avg_price']:.2f}\n"
                response += f"  • Total attendance: {genre['total_reserved']:,}\n\n"
            
            # Format distribution
            format_stats = queryset.values('screen_format').annotate(
                count=Count('id'),
                avg_price=Avg('price')
            ).order_by('-count')[:5]
            
            response += f"## 🎥 Format Distribution\n\n"
            for fmt in format_stats:
                percentage = (fmt['count'] / count) * 100
                response += f"• **{fmt['screen_format']}:** {fmt['count']:,} ({percentage:.1f}%) - "
                response += f"Avg ${fmt['avg_price']:.2f}\n"
            
            # Theater performance
            theater_stats = queryset.values('theater_name', 'theater_city', 'theater_state').annotate(
                showtime_count=Count('id'),
                total_reserved=Sum('reserved'),
                total_capacity=Sum('total_seats'),
                avg_price=Avg('price')
            ).annotate(
                occupancy=ExpressionWrapper(
                    F('total_reserved') * 100.0 / F('total_capacity'),
                    output_field=FloatField()
                )
            ).order_by('-showtime_count')[:10]
            
            response += f"\n## 🏛️ Top Theaters\n\n"
            for i, theater in enumerate(theater_stats, 1):
                response += f"{i}. **{theater['theater_name']}** ({theater['theater_city']}, {theater['theater_state']})\n"
                response += f"   • Showtimes: {theater['showtime_count']:,}\n"
                response += f"   • Occupancy: {theater['occupancy']:.1f}%\n"
                response += f"   • Avg price: ${theater['avg_price']:.2f}\n\n"
            
            return {
                'type': 'analytical',
                'message': response,
                'data': {
                    'overall': overall_stats,
                    'genres': list(genre_stats),
                    'formats': list(format_stats),
                    'theaters': list(theater_stats)
                }
            }
        
        except Exception as e:
            logger.error(f"Error in analysis query: {e}")
            return self._error_response(f"Unable to perform analysis: {str(e)}")
    
    def _handle_list(self, query: str, queryset, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list queries"""
        try:
            count = queryset.count()
            limit = 15
            
            items = queryset.select_related()[:limit]
            filter_desc = self._describe_filters(entities)
            
            response = f"## Movie Listings{filter_desc}\n\n"
            response += f"Found **{count:,} showtimes**. "
            
            if count > limit:
                response += f"Here are the first {limit}:\n\n"
            else:
                response += f"Here are all {count}:\n\n"
            
            for i, item in enumerate(items, 1):
                response += f"### {i}. {item.title}\n"
                response += f"**Theater:** {item.theater_name}, {item.theater_city}, {item.theater_state}\n"
                response += f"**Showtime:** {item.date_sh.strftime('%B %d, %Y')} at {item.time_sh.strftime('%I:%M %p')}\n"
                response += f"**Format:** {item.screen_format} | **Genre:** {item.genre} | **Rating:** {item.rating}\n"
                response += f"**Price:** ${item.price:.2f}\n"
                response += f"**Seats:** {item.available} available out of {item.total_seats}\n\n"
            
            if count > limit:
                response += f"\n_...and {count - limit:,} more showtimes. Refine your search for more specific results._"
            
            return {
                'type': 'analytical',
                'message': response,
                'data': {'count': count, 'filters': entities}
            }
        
        except Exception as e:
            logger.error(f"Error in list query: {e}")
            return self._error_response(f"Unable to list items: {str(e)}")
    
    def handle_comparative_query(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle comparative queries (e.g., IMAX vs Standard, AMC vs Regal)
        """
        try:
            query_lower = query.lower()
            
            # Detect comparison type
            if 'imax' in query_lower and 'standard' in query_lower:
                return self._compare_formats(query, ['IMAX', 'Standard'])
            
            elif 'amc' in query_lower and 'regal' in query_lower:
                return self._compare_theaters(query, ['AMC', 'Regal'])
            
            elif 'weekend' in query_lower and 'weekday' in query_lower:
                return self._compare_day_types(query)
            
            elif '3d' in query_lower and '2d' in query_lower:
                return self._compare_formats(query, ['3D', '2D'])
            
            else:
                # Generic comparison
                return self._generic_comparison(query, entities)
        
        except Exception as e:
            logger.error(f"Error in comparative query: {e}")
            return self._error_response(f"Unable to perform comparison: {str(e)}")
    
    def _compare_formats(self, query: str, formats: List[str]) -> Dict[str, Any]:
        """Compare different screen formats"""
        try:
            response = f"## Comparison: {' vs '.join(formats)}\n\n"
            
            comparison_data = []
            for fmt in formats:
                queryset = Movie.objects.filter(
                    Q(screen_format__icontains=fmt) | Q(movie_format__icontains=fmt)
                )
                
                stats = queryset.aggregate(
                    count=Count('id'),
                    avg_price=Avg('price'),
                    avg_seats=Avg('total_seats'),
                    avg_reserved=Avg('reserved'),
                    avg_available=Avg('available')
                )
                
                if stats['avg_seats'] and stats['avg_seats'] > 0:
                    stats['occupancy'] = (stats['avg_reserved'] / stats['avg_seats']) * 100
                else:
                    stats['occupancy'] = 0
                
                comparison_data.append({
                    'format': fmt,
                    'stats': stats
                })
            
            # Build comparison table
            for data in comparison_data:
                fmt = data['format']
                stats = data['stats']
                
                response += f"### {fmt}\n"
                response += f"• **Showtimes:** {stats['count']:,}\n"
                
                if stats['avg_price']:
                    response += f"• **Average Price:** ${stats['avg_price']:.2f}\n"
                
                if stats['avg_seats']:
                    response += f"• **Average Capacity:** {stats['avg_seats']:.0f} seats\n"
                    response += f"• **Average Occupancy:** {stats['occupancy']:.1f}%\n"
                
                response += "\n"
            
            # Add insights
            if len(comparison_data) == 2:
                fmt1_price = comparison_data[0]['stats']['avg_price'] or 0
                fmt2_price = comparison_data[1]['stats']['avg_price'] or 0
                
                if fmt1_price and fmt2_price:
                    price_diff = abs(fmt1_price - fmt2_price)
                    higher_format = comparison_data[0]['format'] if fmt1_price > fmt2_price else comparison_data[1]['format']
                    
                    response += f"### 💡 Key Insights\n\n"
                    response += f"• **Price Difference:** ${price_diff:.2f}\n"
                    response += f"• {higher_format} is typically more expensive\n"
                    
                    occ1 = comparison_data[0]['stats']['occupancy']
                    occ2 = comparison_data[1]['stats']['occupancy']
                    
                    if occ1 and occ2:
                        more_popular = comparison_data[0]['format'] if occ1 > occ2 else comparison_data[1]['format']
                        response += f"• {more_popular} shows higher occupancy rates\n"
            
            return {
                'type': 'comparative',
                'message': response,
                'data': comparison_data
            }
        
        except Exception as e:
            logger.error(f"Error comparing formats: {e}")
            return self._error_response(f"Unable to compare formats: {str(e)}")
    
    def _compare_theaters(self, query: str, chains: List[str]) -> Dict[str, Any]:
        """Compare different theater chains"""
        try:
            response = f"## Theater Chain Comparison: {' vs '.join(chains)}\n\n"
            
            comparison_data = []
            for chain in chains:
                queryset = Movie.objects.filter(circuit_name__icontains=chain)
                
                stats = queryset.aggregate(
                    count=Count('id'),
                    avg_price=Avg('price'),
                    total_capacity=Sum('total_seats'),
                    total_reserved=Sum('reserved'),
                    unique_theaters=Count('theater_name', distinct=True),
                    unique_movies=Count('title', distinct=True)
                )
                
                if stats['total_capacity'] and stats['total_capacity'] > 0:
                    stats['occupancy'] = (stats['total_reserved'] / stats['total_capacity']) * 100
                else:
                    stats['occupancy'] = 0
                
                comparison_data.append({
                    'chain': chain,
                    'stats': stats
                })
            
            for data in comparison_data:
                chain = data['chain']
                stats = data['stats']
                
                response += f"### {chain}\n"
                response += f"• **Locations:** {stats['unique_theaters']} theaters\n"
                response += f"• **Total Showtimes:** {stats['count']:,}\n"
                response += f"• **Unique Movies:** {stats['unique_movies']}\n"
                
                if stats['avg_price']:
                    response += f"• **Average Ticket Price:** ${stats['avg_price']:.2f}\n"
                
                if stats['total_capacity']:
                    response += f"• **Total Capacity:** {stats['total_capacity']:,} seats\n"
                    response += f"• **Overall Occupancy:** {stats['occupancy']:.1f}%\n"
                
                response += "\n"
            
            return {
                'type': 'comparative',
                'message': response,
                'data': comparison_data
            }
        
        except Exception as e:
            logger.error(f"Error comparing theaters: {e}")
            return self._error_response(f"Unable to compare theaters: {str(e)}")
    
    def _compare_day_types(self, query: str) -> Dict[str, Any]:
        """Compare weekend vs weekday performance"""
        try:
            response = f"## Weekend vs Weekday Comparison\n\n"
            
            # Annotate with day type
            queryset = Movie.objects.annotate(
                day_of_week=ExtractWeekDay('date_sh')
            )
            
            weekend = queryset.filter(day_of_week__in=[1, 7])  # Sunday=1, Saturday=7
            weekday = queryset.filter(day_of_week__in=[2, 3, 4, 5, 6])
            
            weekend_stats = weekend.aggregate(
                count=Count('id'),
                avg_price=Avg('price'),
                total_reserved=Sum('reserved'),
                total_capacity=Sum('total_seats')
            )
            
            weekday_stats = weekday.aggregate(
                count=Count('id'),
                avg_price=Avg('price'),
                total_reserved=Sum('reserved'),
                total_capacity=Sum('total_seats')
            )
            
            response += f"### Weekend (Saturday & Sunday)\n"
            response += f"• **Showtimes:** {weekend_stats['count']:,}\n"
            if weekend_stats['avg_price']:
                response += f"• **Average Price:** ${weekend_stats['avg_price']:.2f}\n"
            if weekend_stats['total_capacity'] and weekend_stats['total_capacity'] > 0:
                weekend_occ = (weekend_stats['total_reserved'] / weekend_stats['total_capacity']) * 100
                response += f"• **Occupancy:** {weekend_occ:.1f}%\n"
            response += "\n"
            
            response += f"### Weekday (Monday-Friday)\n"
            response += f"• **Showtimes:** {weekday_stats['count']:,}\n"
            if weekday_stats['avg_price']:
                response += f"• **Average Price:** ${weekday_stats['avg_price']:.2f}\n"
            if weekday_stats['total_capacity'] and weekday_stats['total_capacity'] > 0:
                weekday_occ = (weekday_stats['total_reserved'] / weekday_stats['total_capacity']) * 100
                response += f"• **Occupancy:** {weekday_occ:.1f}%\n"
            
            return {
                'type': 'comparative',
                'message': response,
                'data': {
                    'weekend': weekend_stats,
                    'weekday': weekday_stats
                }
            }
        
        except Exception as e:
            logger.error(f"Error comparing day types: {e}")
            return self._error_response(f"Unable to compare day types: {str(e)}")
    
    def _generic_comparison(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle generic comparison queries"""
        # Fall back to analytical query
        return self.handle_analytical_query(query, entities)
    
    def handle_conversational_query(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle conversational queries using RAG.
        Optimized for Llama3 8B with smart context management.
        Always provides helpful responses using theater data OR general movie knowledge.
        """
        try:
            # Determine optimal top_k based on query complexity
            query_length = len(query.split())
            
            if query_length < 10:
                top_k = 30  # Simple queries: less context
            elif query_length < 20:
                top_k = 50  # Medium queries: moderate context
            else:
                top_k = 80  # Complex queries: more context
            
            # Add database context if entities found
            database_context = ""
            if entities:
                filters = self.build_database_filters(entities)
                if filters:
                    queryset = Movie.objects.filter(filters)[:10]
                    if queryset.exists():
                        database_context = "\n\n## Relevant Database Records:\n"
                        for item in queryset:
                            database_context += f"• {item.title} at {item.theater_name} "
                            database_context += f"({item.date_sh}, {item.screen_format}, ${item.price})\n"
            
            # Query RAG with optimized parameters
            # Note: Even if no matches, Llama will use its knowledge base
            rag_response = self.rag_service.query(
                query + database_context,
                top_k=top_k,
                return_sources=True
            )
            
            if not rag_response or not rag_response.get('answer'):
                # Fallback: Use Llama's general knowledge with branding
                answer = f"""As Entelligence AI Assistant, I'm here to help with your movie question!

While I don't have specific theater data for this query in my database, I can still provide helpful information about movies, cinema, and entertainment.

{query}

Could you please provide more details about what you'd like to know? I can help with:
• Movie information (plot, cast, reviews, ratings)
• General theater information and formats (IMAX, Dolby, 3D)
• Movie recommendations based on genres or preferences
• Cinema history and interesting movie facts

What would you like to know more about?"""
                
                return {
                    'type': 'conversational',
                    'message': answer,
                    'sources': [],
                    'retrieved_count': 0
                }
            
            answer = rag_response['answer']
            
            # Enhance response if too short - never leave users without helpful info
            if len(answer.split()) < 20:
                if entities and database_context:
                    answer += "\n\n**Additional Context:**" + database_context
                else:
                    # Add a helpful suggestion
                    answer += "\n\nIs there anything specific about this movie or theater you'd like to know? I'm here to help with showtimes, formats, pricing, or general movie information!"
            
            return {
                'type': 'conversational',
                'message': answer,
                'sources': rag_response.get('sources', []),
                'retrieved_count': rag_response.get('retrieved_count', 0)
            }
        
        except Exception as e:
            logger.error(f"Error in conversational query: {e}")
            # Even on error, provide helpful branded response
            return {
                'type': 'conversational',
                'message': f"""Hello! I'm Entelligence AI Assistant, your movie expert.

I encountered a technical issue, but I'm still here to help! Could you rephrase your question? I can assist with:

• **Movie Information**: Plot, cast, director, reviews, ratings
• **Theater Details**: Showtimes, locations, formats (IMAX, 3D, Dolby)
• **Ticket Information**: Prices, availability, seating
• **Recommendations**: Based on genre, mood, or preferences

What would you like to know about movies or theaters?""",
                'sources': [],
                'retrieved_count': 0
            }
    
    def _describe_filters(self, entities: Dict[str, Any]) -> str:
        """Generate natural language description of filters"""
        if not entities:
            return ""
        
        parts = []
        if 'genre' in entities:
            parts.append(f"{entities['genre']} genre")
        if 'rating' in entities:
            parts.append(f"rated {entities['rating']}")
        if 'format' in entities:
            parts.append(f"in {entities['format']} format")
        if 'theater_chain' in entities:
            parts.append(f"at {entities['theater_chain']} theaters")
        if 'state' in entities:
            parts.append(f"in {entities['state']}")
        if 'movie_title' in entities:
            parts.append(f"for '{entities['movie_title']}'")
        
        if parts:
            return " for " + ", ".join(parts)
        return ""
    
    def _error_response(self, error_msg: str) -> Dict[str, Any]:
        """Generate user-friendly branded error response"""
        return {
            'type': 'error',
            'message': f"Hello! I'm **Entelligence AI Assistant**, your movie expert. {error_msg}\n\n**I can help you with:**\n• Movie information (plot, cast, reviews)\n• Theater showtimes and locations\n• Ticket prices and formats (IMAX, 3D, Dolby)\n• Seating availability\n• Movie recommendations\n\nPlease try rephrasing your question, and I'll provide comprehensive assistance!",
            'error': error_msg
        }
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """
        Main entry point: Process any query and return appropriate response.
        Routes to analytical, comparative, or conversational handler.
        """
        try:
            if not query or not query.strip():
                return self._error_response("Empty query received.")
            
            # Extract entities
            entities = self.extract_entities(query)
            
            # Classify query
            query_type = self.classify_query(query)
            
            logger.info(f"Query type: {query_type}, Entities: {entities}")
            
            # Route to appropriate handler
            if query_type == 'comparative':
                return self.handle_comparative_query(query, entities)
            
            elif query_type == 'analytical':
                return self.handle_analytical_query(query, entities)
            
            else:  # conversational
                return self.handle_conversational_query(query, entities)
        
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            return self._error_response(f"an unexpected error occurred: {str(e)}")


# Singleton instance
def get_query_processor():
    """Get singleton query processor instance"""
    if not hasattr(get_query_processor, '_instance'):
        get_query_processor._instance = OptimizedQueryProcessor()
    return get_query_processor._instance

